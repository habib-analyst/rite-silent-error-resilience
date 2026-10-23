# rite — Silent Tool-Error Resilience Harness for Tool-Using Agents

An open, deterministic implementation of the evaluation mechanism in
**arXiv 2610.27777** ("RITE: Evaluating End-to-End Resilience to Silent
Tool Errors in E-Commerce Agentic Systems", Zhang et al., HKUST/Tencent).

**Scope, stated plainly:** this is a *synthetic, deterministic, zero-LLM*
analog of the paper's benchmark — scripted agents + frozen synthetic
e-commerce workflow prefixes + a semantic silent-error taxonomy. It does
**not** replicate the paper's LLM results; it tests whether the paper's
core ordering reproduces with scripted agents on synthetic traces, and it
measures a verification-path intervention honestly. CPU only, $0, fully
reproducible via `run_experiment.py --seed`.

**#56 collision note:** tool-trace-audit (#56) audits tool traces for
prediction-time *label leakage*; RITE tests agent *recovery* after silent
corruption. Adjacent, not overlapping — different question, different
artifact.

## What it does

For each of 167 matched units across 9 synthetic e-commerce workflows
(cheapest-in-stock, order lookup, refund check, bundle total, restock list,
shipping quote, price audit, coupon best, top seller), the harness:

1. Freezes a workflow prefix and injects a **plausible-but-wrong** tool
   value from an 8-class semantic taxonomy (price swap/drift, product swap,
   stock, rating, shipping, status mislabel, discount misread) — with no
   failure signal (the *silent-error* arm).
2. Runs the same unit with the correct value (*correct-value* arm) and with
   an explicit tool failure at the same step (*explicit-failure* arm).
3. Lets a scripted deterministic agent continue freely and scores whether
   it completes the original query (exact match vs ground truth).
4. Runs a **verification-path arm** (the paper's "State Checker"): before
   finalizing, the agent re-queries load-bearing values through an
   independent secondary feed and corrects mismatches.

## Measured results (locked kill-gates, seeds 42 / 20261022)

| arm | success |
|---|---|
| baseline, correct value | 1.0000 |
| baseline, silent error | 0.0000 (-100.00pp, 95% CI [-100.00, -100.00]) |
| baseline, explicit failure | 1.0000 (retry recovers) |
| verify-path, silent error | 0.6886 (+68.86pp recovery, 95% CI [61.68, 76.05]) |

The paper's ordering reproduces: silent errors are strictly harder than
explicit failures. Recovery is complete for taxonomy classes covered by a
verify tool (price/discount/status/stock: 100%) and zero for classes with
no verification path (product swap, rating/shipping drift) — the paper's
successive bottlenecks (recognition -> verification use -> evidence
integration) made concrete.

**Read the numbers honestly:** the -100pp silent drop is an *upper bound
by construction* — the baseline agent has no recognition mechanism at all,
and the pre-registered decisiveness filter keeps only consequential
injections. The paper's LLMs land near ~50pp because they partially
recover. This harness demonstrates the mechanism and the ordering and
measures the intervention; it does not discover the effect size. See
`KILLGATE.md` (honesty appendix) and `papers/rite/PAPER.md` (Limits).

## Reproduce

```bash
python -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python run_experiment.py --seed 42 --out results/results_seed42.json
.venv/bin/python -m pytest tests/ -q   # 15 tests
```

Determinism: fixed seeds everywhere; seed 20261022 replicates all gate
verdicts. Statistics: paired bootstrap, B=2000, seed 7, 95% percentile CIs.

## Layout

- `src/rite/world.py` — synthetic catalog + deterministic tool simulator
  (sticky silent corruption, transient explicit failure, verify tools)
- `src/rite/workflows.py` — the nine e-commerce workflows
- `src/rite/errors.py` — the 8-class silent-error taxonomy + plausibility
  checks
- `src/rite/agents.py` — baseline + verification-path (State Checker) agents
- `src/rite/experiment.py` — matched-unit generation (decisiveness filter),
  resume-from-records evaluation under `flock -n`
- `src/rite/stats.py`, `src/rite/gates.py` — paired bootstrap + locked gates
- `run_experiment.py` — CLI (`--seed`, `--out`, `--units`)
- `KILLGATE.md` / `PREREG.md` — pre-registered protocol, locked before
  measurement

## License

MIT. Synthetic data only; no affiliation with the paper authors.
