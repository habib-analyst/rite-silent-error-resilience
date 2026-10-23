"""Experiment driver: unit generation, matched-condition evaluation.

Matched design: each unit is evaluated under three conditions
(correct-value / silent-error / explicit-failure) with the baseline agent,
plus the verify agent on the silent-error arm (and on the correct arm as a
clean-run sanity check). Deterministic given the experiment seed.

Resume-from-records: results are appended per unit under an flock -n guard
so a replayed background launch cannot duplicate-writes contaminate the
records (hard-won infra rule).
"""

import json
import os
import random

import fcntl

from .world import Catalog, ToolView
from .workflows import WORKFLOWS
from .agents import BaselineAgent, VerifyAgent
from .errors import check_plausible

UNIT_COUNTS = [19, 19, 19, 19, 19, 18, 18, 18, 18]  # sums to 167


def _true_of(catalog, tool, args):
    view = ToolView(catalog)
    return getattr(view, tool)(*args)


def generate_units(seed, n_target=167, max_resample=25):
    """Generate matched units with the pre-registered decisiveness filter.

    A unit is kept only if the baseline agent's answer on the corrupted
    prefix differs from its answer on the correct prefix (a silent error
    that cannot change the answer is not an error). Returns
    (units, shortfall, attempts_log).
    """
    catalog = Catalog(seed)
    rng = random.Random(seed ^ 0x0E17)
    units = []
    shortfall = 0
    attempts_log = []
    wf_cycle = []
    for i, c in enumerate(UNIT_COUNTS):
        wf_cycle.extend([WORKFLOWS[i]] * c)
    assert len(wf_cycle) == sum(UNIT_COUNTS)
    wf_cycle = wf_cycle[:n_target]
    assert len(wf_cycle) == n_target
    baseline = BaselineAgent()
    uid = 0
    for wf in wf_cycle:
        made = False
        attempts = 0
        while not made and attempts < max_resample * 3:
            attempts += 1
            params = wf.generate(rng, catalog)
            corr_class = rng.choice(wf.applicable)
            try:
                spec = wf.make_corrupt_spec(catalog, params, corr_class, rng)
            except (IndexError, ValueError):
                continue
            true_v = _true_of(catalog, spec["tool"], spec["args"])
            try:
                check_plausible(corr_class, spec["tool"], spec["args"],
                                spec["value"], true_v)
            except AssertionError:
                continue
            # decisiveness filter: baseline answer must change under corruption
            clean_view = ToolView(catalog)
            ans_clean, ok_clean = baseline.run(wf, clean_view, params)
            corr_view = ToolView(catalog, corrupt={
                "tool": spec["tool"], "args": tuple(spec["args"]),
                "kind": "silent", "value": spec["value"]})
            ans_corr, ok_corr = baseline.run(wf, corr_view, params)
            if ok_clean and ok_corr and ans_clean != ans_corr:
                units.append({
                    "unit_id": "u%04d" % uid,
                    "workflow": wf.name,
                    "params": params,
                    "corr_class": corr_class,
                    "corr_tool": spec["tool"],
                    "corr_args": list(spec["args"]),
                    "corr_value": spec["value"],
                })
                uid += 1
                made = True
        attempts_log.append({"workflow": wf.name, "attempts": attempts,
                             "made": made})
        if not made:
            shortfall += 1
    return units, shortfall, attempts_log, catalog


def run_unit(unit, catalog):
    """Evaluate one unit under all matched conditions. Returns a record."""
    from .workflows import WORKFLOW_BY_NAME
    wf = WORKFLOW_BY_NAME[unit["workflow"]]
    baseline = BaselineAgent()
    verify = VerifyAgent()
    truth = wf.ground_truth(catalog, unit["params"])
    spec = {"tool": unit["corr_tool"], "args": tuple(unit["corr_args"])}

    def _succ(agent_run):
        ans, ok = agent_run[0], agent_run[1]
        return bool(ok and ans == truth)

    rec = {"unit_id": unit["unit_id"], "workflow": unit["workflow"],
           "corr_class": unit["corr_class"]}
    # baseline x 3 matched conditions
    v = ToolView(catalog)
    rec["baseline_correct"] = int(_succ(baseline.run(wf, v, unit["params"])))
    v = ToolView(catalog, corrupt=dict(spec, kind="silent",
                                       value=unit["corr_value"]))
    rec["baseline_silent"] = int(_succ(baseline.run(wf, v, unit["params"])))
    v = ToolView(catalog, corrupt=dict(spec, kind="explicit",
                                       value=unit["corr_value"]))
    rec["baseline_explicit"] = int(_succ(baseline.run(wf, v, unit["params"])))
    # verify agent on silent arm (+ correct arm sanity)
    v = ToolView(catalog, corrupt=dict(spec, kind="silent",
                                       value=unit["corr_value"]))
    ans, ok, recovered, n_verify = verify.run(wf, v, unit["params"])
    rec["verify_silent"] = int(bool(ok and ans == truth))
    rec["verify_recovered_flag"] = int(bool(recovered))
    rec["verify_calls"] = int(n_verify)
    v = ToolView(catalog)
    ans, ok, recovered, n_verify = verify.run(wf, v, unit["params"])
    rec["verify_correct"] = int(bool(ok and ans == truth))
    return rec


def _load_results(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"records": [], "units": []}


def run_experiment(seed, out_path, n_target=167):
    """Run (or resume) the full battery. Returns the results dict."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    # flock -n guard: a replayed launch must not duplicate-write records.
    lock_path = out_path + ".lock"
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("results file is locked by another run; refusing "
                           "to duplicate-write: %s" % out_path)
    try:
        results = _load_results(out_path)
        if not results.get("units"):
            units, shortfall, attempts_log, _ = generate_units(seed, n_target)
            results["seed"] = seed
            results["units"] = units
            results["shortfall"] = shortfall
            results["attempts_log"] = attempts_log
        catalog = Catalog(seed)
        done = {r["unit_id"] for r in results["records"]}
        for unit in results["units"]:
            if unit["unit_id"] in done:
                continue
            results["records"].append(run_unit(unit, catalog))
            done.add(unit["unit_id"])
            # incremental flush so a kill loses at most one unit
            with open(out_path, "w") as f:
                json.dump(results, f)
        with open(out_path, "w") as f:
            json.dump(results, f)
        return results
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
