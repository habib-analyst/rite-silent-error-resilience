"""Tests for the RITE deterministic harness (all must be green)."""
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rite.world import Catalog, ToolView, ToolError
from rite.workflows import WORKFLOWS, WORKFLOW_BY_NAME
from rite.agents import BaselineAgent, VerifyAgent
from rite.errors import TAXONOMY, RECOVERABLE, UNRECOVERABLE, check_plausible
from rite.experiment import generate_units, run_unit
from rite.stats import paired_bootstrap_ci
from rite.gates import evaluate_gates


def test_catalog_deterministic():
    a, b = Catalog(42), Catalog(42)
    assert a.products == b.products
    assert a.orders == b.orders
    c = Catalog(43)
    assert a.products != c.products


def test_nine_workflows_present():
    assert len(WORKFLOWS) == 9
    assert len(WORKFLOW_BY_NAME) == 9


def test_baseline_perfect_on_correct_traces():
    """Disease-first sanity: baseline must be competent on clean traces."""
    catalog = Catalog(7)
    baseline = BaselineAgent()
    rng = random.Random(7)
    for wf in WORKFLOWS:
        for _ in range(3):
            params = wf.generate(rng, catalog)
            view = ToolView(catalog)
            ans, ok = baseline.run(wf, view, params)
            assert ok, wf.name
            assert ans == wf.ground_truth(catalog, params), wf.name


def test_taxonomy_plausibility_on_generated_specs():
    catalog = Catalog(11)
    rng = random.Random(11)
    for wf in WORKFLOWS:
        for _ in range(5):
            params = wf.generate(rng, catalog)
            cls = rng.choice(wf.applicable)
            try:
                spec = wf.make_corrupt_spec(catalog, params, cls, rng)
            except (IndexError, ValueError):
                continue
            view = ToolView(catalog)
            true_v = getattr(view, spec["tool"])(*spec["args"])
            check_plausible(cls, spec["tool"], spec["args"], spec["value"], true_v)


def test_silent_corruption_is_sticky():
    catalog = Catalog(5)
    view = ToolView(catalog, corrupt={"tool": "get_price", "args": ("P0001",),
                                      "kind": "silent", "value": 12345})
    assert view.get_price("P0001") == 12345
    assert view.get_price("P0001") == 12345  # sticky, not transient


def test_explicit_failure_recovers_on_retry():
    catalog = Catalog(5)
    view = ToolView(catalog, corrupt={"tool": "get_price", "args": ("P0001",),
                                      "kind": "explicit", "value": 999})
    with pytest.raises(ToolError):
        view.get_price("P0001")
    true_v = ToolView(catalog).get_price("P0001")
    assert view.get_price("P0001") == true_v  # retry returns true value


def test_verify_tools_never_corrupted():
    catalog = Catalog(5)
    view = ToolView(catalog, corrupt={"tool": "get_price", "args": ("P0001",),
                                      "kind": "silent", "value": 12345})
    assert view.verify_price("P0001") == ToolView(catalog).get_price("P0001")


def test_verify_agent_recovers_price_swap():
    """State Checker mechanism: independent feed catches a sticky corruption."""
    catalog = Catalog(21)
    wf = WORKFLOW_BY_NAME["bundle_total"]
    rng = random.Random(21)
    params = wf.generate(rng, catalog)
    spec = wf.make_corrupt_spec(catalog, params, "price_swap", rng)
    truth = wf.ground_truth(catalog, params)
    baseline, verify = BaselineAgent(), VerifyAgent()
    v = ToolView(catalog, corrupt={"tool": spec["tool"],
                                   "args": tuple(spec["args"]),
                                   "kind": "silent", "value": spec["value"]})
    ans_b, ok_b = baseline.run(wf, v, params)
    assert ok_b and ans_b != truth  # silent error hurts
    v = ToolView(catalog, corrupt={"tool": spec["tool"],
                                   "args": tuple(spec["args"]),
                                   "kind": "silent", "value": spec["value"]})
    ans_v, ok_v, recovered, n_calls = verify.run(wf, v, params)
    assert ok_v and recovered and ans_v == truth and n_calls > 0


def test_verify_agent_cannot_recover_product_swap():
    """Honest bound: no verify tool covers product identity."""
    catalog = Catalog(33)
    wf = WORKFLOW_BY_NAME["cheapest_in_stock"]
    rng = random.Random(33)
    for _ in range(20):  # find a decisive product_swap unit
        params = wf.generate(rng, catalog)
        spec = wf.make_corrupt_spec(catalog, params, "product_swap", rng)
        truth = wf.ground_truth(catalog, params)
        baseline = BaselineAgent()
        v = ToolView(catalog, corrupt={"tool": spec["tool"],
                                       "args": tuple(spec["args"]),
                                       "kind": "silent",
                                       "value": spec["value"]})
        ans_b, ok_b = baseline.run(wf, v, params)
        if ok_b and ans_b != truth:
            break
    else:
        pytest.skip("no decisive product_swap found")
    verify = VerifyAgent()
    v = ToolView(catalog, corrupt={"tool": spec["tool"],
                                   "args": tuple(spec["args"]),
                                   "kind": "silent", "value": spec["value"]})
    ans_v, ok_v, recovered, _ = verify.run(wf, v, params)
    assert not recovered and ans_v != truth  # unrecoverable by design


def test_explicit_failure_arm_recovers_via_retry():
    catalog = Catalog(44)
    wf = WORKFLOW_BY_NAME["bundle_total"]
    rng = random.Random(44)
    params = wf.generate(rng, catalog)
    spec = wf.make_corrupt_spec(catalog, params, "price_swap", rng)
    truth = wf.ground_truth(catalog, params)
    baseline = BaselineAgent()
    v = ToolView(catalog, corrupt={"tool": spec["tool"],
                                   "args": tuple(spec["args"]),
                                   "kind": "explicit",
                                   "value": spec["value"]})
    ans, ok = baseline.run(wf, v, params)
    assert ok and ans == truth  # observable failure -> retry -> recover


def test_bootstrap_ci_deterministic_and_sane():
    diffs = [-1] * 70 + [0] * 30
    m1, lo1, hi1 = paired_bootstrap_ci(diffs, B=2000, seed=7)
    m2, lo2, hi2 = paired_bootstrap_ci(diffs, B=2000, seed=7)
    assert (m1, lo1, hi1) == (m2, lo2, hi2)
    assert abs(m1 - (-0.7)) < 1e-9
    assert hi1 < 0  # excludes 0


def test_generate_units_deterministic_and_decisive():
    u1, s1, _, _ = generate_units(99, n_target=27)
    u2, s2, _, _ = generate_units(99, n_target=27)
    assert u1 == u2 and s1 == s2 == 0
    assert len(u1) == 27
    # n=27 covers the first two workflows (19 + 8 of the second block)
    assert {u["workflow"] for u in u1} == \
        {WORKFLOWS[0].name, WORKFLOWS[1].name}


def test_run_unit_record_schema():
    catalog = Catalog(55)
    units, _, _, _ = generate_units(55, n_target=9)
    rec = run_unit(units[0], catalog)
    for k in ["baseline_correct", "baseline_silent", "baseline_explicit",
              "verify_silent", "verify_correct", "verify_recovered_flag",
              "verify_calls"]:
        assert k in rec, k
    assert rec["verify_calls"] >= 0


def test_gates_evaluate_on_synthetic_records():
    recs = []
    for i in range(40):
        recs.append({
            "unit_id": "u%04d" % i, "workflow": "w",
            "corr_class": "price_swap",
            "baseline_correct": 1,
            "baseline_silent": 0 if i < 32 else 1,   # 80% drop
            "baseline_explicit": 1,
            "verify_silent": 1 if i < 28 else 0,      # strong recovery
            "verify_correct": 1,
            "verify_recovered_flag": 1 if i < 28 else 0,
            "verify_calls": 4,
        })
    g = evaluate_gates(recs)
    assert g["g2a"]["pass"] and g["g2b"]["pass"] and g["g2c"]["pass"]
    assert g["g3"]["pass"] and g["verdict"] == "PASS"


def test_taxonomy_inventory_matches_prereg():
    assert TAXONOMY == ["price_swap", "price_drift", "product_swap",
                        "stock_plausible", "rating_drift", "shipping_drift",
                        "status_mislabel", "discount_misread"]
    assert RECOVERABLE | UNRECOVERABLE == set(TAXONOMY)
    assert not (RECOVERABLE & UNRECOVERABLE)
