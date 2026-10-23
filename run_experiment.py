#!/usr/bin/env python3
"""run_experiment.py --seed 42 --out results/results_seed42.json [--units 167]

Deterministic end-to-end battery: generate matched units, evaluate all
arms, compute the locked kill-gate verdicts, write results JSON.
Resume-safe: completed unit records are skipped; the results file is
flock -n guarded against duplicate writers.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from rite.experiment import run_experiment
from rite.gates import evaluate_gates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--units", type=int, default=167)
    args = ap.parse_args()

    results = run_experiment(args.seed, args.out, n_target=args.units)
    gates = evaluate_gates(results["records"])
    results["gates"] = gates
    with open(args.out, "w") as f:
        json.dump(results, f)

    print("seed=%d n=%d shortfall=%d" % (args.seed, gates["n"],
                                         results.get("shortfall", 0)))
    print("baseline correct : %.4f" % gates["baseline_correct_rate"])
    print("baseline silent  : %.4f" % gates["baseline_silent_rate"])
    print("baseline explicit: %.4f" % gates["baseline_explicit_rate"])
    print("verify silent    : %.4f" % gates["verify_silent_rate"])
    print("verify correct   : %.4f" % gates["verify_correct_rate"])
    print("mean verify calls: %.2f" % gates["mean_verify_calls"])
    g = gates
    print("G2a baseline>=80%% : %s (%.4f)" % (g["g2a"]["pass"], g["g2a"]["rate"]))
    print("G2b silent drop   : %s (%.2fpp CI [%.2f, %.2f])"
          % (g["g2b"]["pass"], g["g2b"]["mean_drop_pp"], *g["g2b"]["ci_pp"]))
    print("G2c silent>explicit: %s (silent %.2fpp vs explicit %.2fpp, diff CI [%.2f, %.2f])"
          % (g["g2c"]["pass"], g["g2c"]["mean_silent_drop_pp"],
             g["g2c"]["mean_explicit_drop_pp"], *g["g2c"]["diff_ci_pp"]))
    print("G3  recovery      : %s (%.2fpp CI [%.2f, %.2f])"
          % (g["g3"]["pass"], g["g3"]["mean_recovery_pp"], *g["g3"]["ci_pp"]))
    print("VERDICT: %s" % gates["verdict"])


if __name__ == "__main__":
    main()
