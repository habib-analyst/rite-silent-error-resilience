# BUILD_NOTES.md — RITE build log (project #62)

## 2026-10-22 ~10:15 PKT — dispatch received
Kill-gate-first builder task for arXiv 2610.27777 (RITE). Work dir
~/workspace/build/rite/. Infra: project-local venv (.venv, pytest only —
no pip install --break-system-packages), no network calls in code, CPU only.

## Gate 1 — live verification (~10:20 PKT)
- arXiv abs page fetched live via curl (43148 bytes, /tmp/rite_abs_live.html):
  zero github.com links, zero code-link markers. Title tag confirms paper.
- GitHub repo search API (unauthenticated): "2610.27777" -> 0,
  "RITE silent tool error" -> 0, "silent tool error resilience agents" -> 0,
  "rite silent-error resilience" -> 0 (all incomplete_results=false).
- Web search: only a third-party Zotpaper digest + unrelated papers. No
  author implementation, no benchmark data.
- Slug check: habib-analyst/rite-silent-error-resilience -> API 404 (free).
- **Gate 1 PASS.** KILLGATE.md + PREREG.md written and LOCKED before any
  measurement (bars: G2a >=80%, G2b <=-20pp CI excl 0, G2c ordering CI excl
  0, G3 >=+10pp CI excl 0; seeds 42 / 20261022; bootstrap B=2000 seed 7).

## Design (locked in PREREG.md)
- Synthetic catalog: 12 categories x 8 products, orders, sellers, discount
  codes, seeded RNG. Deterministic ToolView with sticky silent corruption
  and transient explicit failure (fail-once, retry recovers).
- 9 workflows x 167 matched units (19,19,19,19,19,18,18,18,18) x 3
  conditions = 501 instances, mirroring the paper's 167/501 structure.
- 8-class semantic taxonomy; injected values always plausible (same schema,
  in-distribution, drawn from the catalog); plausibility enforced by
  errors.check_plausible and covered by tests.
- Baseline: canonical plan, trusts outputs, retry-once on explicit failure.
- VerifyAgent (State Checker arm): pre-finalization re-query of load-bearing
  values (price/stock/order-status/discount) via independent verify tools;
  mismatch -> replace + recompute. product_swap / rating_drift /
  shipping_drift have no verify tool -> honestly unrecoverable (bounds
  recovery < 100%, the paper's successive bottlenecks made concrete).
- Decisiveness filter: unit kept only if the full baseline run's answer
  differs under corruption (pre-registered; up to 75 attempts/slot,
  shortfall documented — got 0).

## Build bugs caught by tests (honest engineering log)
1. `0xCATA10` invalid hex literal (T not hex) -> `0xCA7A10`.
2. price_drift clamped at the 999 floor could equal the true price ->
   `_drifted()` helper guarantees difference (+137 nudge).
3. check_plausible assumed scalar forms; W6 (quote list) and W9 (seller
   list) use composite forms of the same semantic classes -> extended
   plausibility rules for those forms (documented in errors.py).
4. generate_units asserted cycle length == n_target, breaking small-n test
   runs -> slice-then-assert.

## Measurement (locked battery)
- Smoke: n=20 seed 42 -> all gates PASS (0.3s).
- Primary seed 42, n=167: G2a 1.0000 | G2b -100.00pp CI [-100,-100] |
  G2c silent -100pp vs explicit 0.00pp, diff CI [-100,-100] |
  G3 +68.86pp CI [61.68, 76.05]. shortfall=0.
- Replication seed 20261022: identical verdicts; G3 +65.87pp CI
  [58.68, 73.05]. Not seed-luck.
- 15/15 tests green (pytest).
- Per-class recovery: discount_misread/price_drift/status_mislabel/
  stock_plausible -> 100%; price_swap -> 0.63/0.57 (W6 quote-cost form has
  no verify tool); product_swap/rating_drift/shipping_drift -> 0%.
- Mean verification calls per unit: 4.96 (the State Checker's cost).

## Deviation / honesty notes
- No protocol deviations: the battery ran exactly per PREREG.md.
- Interpretation caveat (documented in KILLGATE.md + PAPER.md): the -100pp
  silent drop is an upper bound BY CONSTRUCTION (decisiveness filter +
  zero-recognition baseline), vs the paper's ~50pp for LLMs that partially
  recover. The experiment demonstrates the mechanism and the ordering and
  honestly measures the verification-path recovery — it does not discover
  the effect size. Stated plainly in README + PAPER so nobody misreads it.
- W6 ship_quote applies the price_swap class to quote costs and W9
  top_seller applies rating_drift to seller ratings (same semantic classes,
  composite value forms) — documented in workflows.py + errors.py, not new
  taxonomy classes.
- Explicit-failure model is transient (fail once, retry recovers) per
  PREREG; the retry-twice-fails fallback path in agents.py is therefore
  dead code under this protocol (kept for protocol fidelity, noted here).

## Deliverables
- Repo code: ~/workspace/build/rite/ (src/rite 6 modules, tests 15 green,
  run_experiment.py CLI, README, LICENSE, requirements.txt, results JSONs)
- Push payload: hidden_files/rite_push_payload.json (repo
  habib-analyst/rite-silent-error-resilience, no .github/workflows)
- Paper: hidden_files/papers/rite/PAPER.md
- LinkedIn draft: hidden_files/linkedin_drafts/rite.md
- This project makes NO pushes (builder cannot push; parent handles repo
  creation + push via approval card).
