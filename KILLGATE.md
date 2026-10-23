# KILLGATE.md — RITE silent-error resilience harness (project #62)

Pre-registered 2026-10-22 BEFORE any measurement run. Thresholds below are
locked now; the final battery runs AFTER this file is written. No goalpost-
moving: bars were fixed before seeing a single measured number.

## Paper

arXiv 2610.27777 — "RITE: Evaluating End-to-End Resilience to Silent Tool
Errors in E-Commerce Agentic Systems" (Zhang, Lin, Sun, Lin, Sheng, He, Gao,
Jikai, Rong; HKUST/Tencent; submitted 2026-10-20).

Paper facts: tool-using LLM agents answer e-commerce queries via multi-step
tool interactions; a plausible-but-wrong tool value can be returned WITHOUT an
explicit failure signal ("silent error") and propagate into final answers. The
paper formulates the Silent-error Resilience Task (does the agent complete the
original query after a silent error corrupts an intermediate state?) and the
RITE benchmark: 167 matched units across nine e-commerce workflows, 501
instances (silent-error / correct-value / explicit-failure). Headline findings
across 10 LLMs: silent errors roughly halve task success and are consistently
HARDER than explicit failures. Successive bottlenecks: recognition, use of an
available verification path, integration of the resulting evidence. They
propose a light "State Checker" intervention.

**Our artifact is a deterministic, zero-LLM, synthetic analog** — scripted
agents + frozen synthetic e-commerce workflow prefixes + a semantic silent-
error taxonomy. It does NOT replicate the paper's LLM benchmark; it tests
whether the paper's core ordering (silent hurts more than explicit; a
verification path recovers part of the loss) reproduces with scripted agents
on synthetic traces. Stated as such in README and PAPER.

**#56 collision note:** tool-trace-audit (#56, PUSHED LIVE) audits tool traces
for prediction-time label leakage; RITE tests agent RECOVERY after silent
corruption. Adjacent, not overlapping — different question, different artifact.

## Gate 1 — author code / benchmark data absent (live re-verification)

Checked 2026-10-22 ~10:10 PKT, unauthenticated:

1. arXiv abs page fetched live via curl
   (https://arxiv.org/abs/2610.27777, 43148 bytes, saved to /tmp/rite_abs_live.html):
   ZERO `github.com` links, zero code-link markers. Title tag confirms the
   paper identity.
2. GitHub repo search API (unauthenticated, rate limit healthy), all
   `total_count = 0`, `incomplete_results = false`:
   - `q=2610.27777`
   - `q="RITE silent tool error"`
   - `q=silent tool error resilience agents`
   - `q=rite silent-error resilience`
3. Web search: only a third-party Zotpaper digest and unrelated papers; NO
   author implementation, NO released benchmark data.
4. Repo slug collision: `habib-analyst/rite-silent-error-resilience` returns
   GitHub API 404 (free).

**Verdict: PASS.** First open implementation claim stands. (If any of 1-3 had
shown author code or benchmark data, the project would KILL immediately.)

## Gate 2 — DISEASE-FIRST (pre-registered)

Setup: n=167 matched units across 9 synthetic e-commerce workflows (see
PREREG.md), each evaluated under 3 matched conditions (correct-value /
silent-error / explicit-failure) = 501 instances, mirroring the paper's
structure. Scripted baseline agent: trusts tool outputs, retries once on
explicit failure then falls back to the prefix-cached value (pre-registered
behavior — explicit failures are OBSERVABLE, so recovery is the honest
mechanism behind the paper's ordering).

- **G2a:** baseline success on correct-value traces >= 0.80 (agents must work
  at all first; #47 lesson).
- **G2b:** mean(silent - correct) <= -0.20 (a >=20pp drop) AND paired
  bootstrap (B=2000, fixed RNG seed 7) 95% percentile CI for the per-unit
  paired difference excludes 0 (upper bound < 0).
- **G2c:** the silent drop is LARGER than the explicit-failure drop (the
  paper's ordering): mean(silent - correct) < mean(explicit - correct) AND
  paired bootstrap 95% CI for (d_silent - d_explicit) excludes 0
  (upper bound < 0).
- **KILL** if any of G2a/G2b/G2c fails. No forcing, no re-tuning the taxonomy
  to manufacture the effect.

Honest risk, stated up front: the explicit-failure retry may recover ~fully,
making G2c nearly equivalent to G2b; if silent errors do not move the needle
at this scale, the project dies here.

## Gate 3 — LOAD-BEARING (pre-registered)

Setup: verification-path arm ("State Checker" analog): before finalizing, the
agent re-queries each load-bearing observed value (price, stock, order status,
discount — pre-registered set) through an INDEPENDENT secondary-feed verify
tool; on mismatch it replaces the value and recomputes the answer. Corruption
is sticky on the corrupted (tool, args) pair, so same-tool re-query cannot
recover — recovery must come from the independent path. Taxonomy classes
without a verify tool (product-id swap, rating drift, shipping drift) are
honestly unrecoverable and bound recovery below 100%.

- **G3:** mean(verify_silent - baseline_silent) >= +0.10 (recovers >=10pp of
  the silent-error loss) AND paired bootstrap (B=2000, seed 7) 95% CI
  excludes 0 (lower bound > 0).
- **KILL** otherwise.

## Replication bar (pre-registered)

Primary seed 42; determinism check on seed 20261022 must produce the same
PASS/KILL verdicts on all three gates (verdict-level replication, not
CI-identity). Bootstrap RNG seed 7 fixed for both.

## Measured verdict (final battery 2026-10-22)

Primary seed 42, n=167 matched units (501 instances), shortfall=0.
Replication seed 20261022: identical verdicts on all gates.

| measure | seed 42 | seed 20261022 |
|---|---|---|
| baseline correct-value success | 1.0000 (167/167) | 1.0000 |
| baseline silent-error success | 0.0000 (0/167) | 0.0000 |
| baseline explicit-failure success | 1.0000 (167/167) | 1.0000 |
| verify-agent silent-error success | 0.6886 (115/167) | 0.6587 (110/167) |
| verify-agent correct-value success (sanity) | 1.0000 | 1.0000 |
| mean verification calls / unit | 4.96 | 4.93 |

- **Gate 1: PASS** (live-verified above, 2026-10-22).
- **Gate 2a: PASS** — baseline correct-value rate 1.0000 >= 0.80.
- **Gate 2b: PASS** — silent drop **-100.00pp**, paired bootstrap 95% CI
  **[-100.00, -100.00]** (B=2000, seed 7), excludes 0, bar <= -20pp met.
- **Gate 2c: PASS** — silent (-100.00pp) hurts more than explicit (0.00pp);
  paired CI of (d_silent - d_explicit) = **[-100.00, -100.00]**, excludes 0.
  The paper's ordering reproduces.
- **Gate 3: PASS** — verification-path recovery **+68.86pp**, paired
  bootstrap 95% CI **[61.68, 76.05]**, excludes 0, bar >= +10pp met.
  Replication seed: +65.87pp, CI [58.68, 73.05].

**Verdict: PASS.** Staged for push (payload in
hidden_files/rite_push_payload.json; repo creation + push by parent —
builder makes no pushes).

**Honesty appendix (what the numbers do and do not mean):** the -100pp
silent drop is an UPPER BOUND by construction, not a discovered effect size:
(1) the pre-registered decisiveness filter keeps only injections that flip
the baseline's full-run answer (a non-consequential injection is not a
silent error, as in the paper); (2) the baseline agent has NO recognition
mechanism at all — the most extreme point of the paper's bottleneck
spectrum, where the paper's LLMs land near ~50pp because they partially
recognize/recover. Likewise the explicit arm's 100% recovery follows from
the pre-registered transient-failure + retry-once model. What is genuinely
demonstrated: the 8-class taxonomy yields decisive silent errors across all
9 workflows; the paper's ORDERING (silent strictly harder than explicit)
reproduces; and the State Checker arm recovers 68.86pp with recovery
exactly tracking verify-tool coverage (recoverable classes: 100%;
product_swap / rating_drift / shipping_drift / quote-cost: 0% — the
paper's successive bottlenecks made concrete). Full discussion in
papers/rite/PAPER.md ("Limits").
