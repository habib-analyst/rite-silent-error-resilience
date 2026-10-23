# PREREG.md — RITE harness experimental design (LOCKED 2026-10-22, pre-measurement)

Immutable protocol. Any deviation after measurement is documented in
BUILD_NOTES.md + PAPER.md as a deviation, never silently applied.

## 1. World model (synthetic, seeded)

`src/rite/world.py`: a synthetic e-commerce catalog generated from a seeded
RNG. 12 categories x ~8 products with plausible names, prices (lognormal-ish,
in cents), stock counts, ratings (3.0-5.0), shipping days, sellers (id,
rating, sales), discount codes (code -> fraction), orders (id -> status,
eta_days, total_cents, days_since_delivery). ALL synthetic, documented as
synthetic in README. No real merchant data.

## 2. Tools (deterministic simulator)

Primary tools: `search_products(category, max_price)` -> [product_id];
`get_price(pid)` -> cents; `get_stock(pid)` -> int; `get_rating(pid)` ->
float; `get_shipping_days(pid)` -> int; `get_category(pid)` -> str;
`check_discount(code)` -> fraction; `get_order(oid)` -> dict(status,
eta_days, total_cents, days_since); `get_seller(pid)` -> [(seller_id,
rating, sales)]; `get_shipping_quote(pid, dest)` -> [(carrier, cost_cents)].

Verification-path tools (independent secondary feed, TRUE values):
`verify_price(pid)`, `verify_stock(pid)`, `verify_order_status(oid)`,
`verify_discount(code)`. Available to every agent but used ONLY by the
verification-path arm (and by workflow 7's audit as primary data — see 3).

## 3. The nine workflows (mirror the paper's nine e-commerce workflows)

1. `cheapest_in_stock(category, budget_c, min_rating, code)`:
   search -> attrs per product -> filter (stock>0, price<=budget,
   rating>=min) -> cheapest -> discount -> answer (pid, total_cents).
2. `order_lookup(oid)`: get_order -> answer (status, eta_days).
3. `refund_check(oid, policy_days)`: get_order -> eligible = (status ==
   "delivered" and days_since <= policy_days) -> answer (eligible,
   refund_cents).
4. `bundle_total(pids, code)`: get_price each + check_discount ->
   answer total_cents.
5. `restock_list(category, threshold)`: search -> get_stock each ->
   answer sorted [pid with stock < threshold].
6. `ship_quote(pid, dest)`: get_shipping_quote -> answer (cheapest
   carrier, cost_cents).
7. `price_audit(category, tol)`: search -> get_price each; flag where
   |price - category_median| / median > tol -> answer sorted [pid].
   (Baseline uses get_price only; the median comparison is its audit rule.)
8. `coupon_best(pids, codes)`: get_price each + check_discount each ->
   answer (best_code, total_cents).
9. `top_seller(pid, min_sales)`: get_seller -> filter sales >= min ->
   max rating -> answer seller_id.

The "frozen prefix" per unit: the canonical plan's first attribute-bearing
tool call(s). Corruption is injected at the FIRST plan step whose output
class is in the taxonomy (see 4); everything before it (e.g. the search)
is the frozen prefix.

## 4. Semantic silent-error taxonomy (8 classes, fixed)

Injected values are plausible: same schema, in-distribution, drawn from the
catalog (never out-of-range garbage):

- `price_swap`: replace price with a REAL price of another product in the
  same category.
- `price_drift`: price shifted by a realistic delta (+/-5-15%) chosen to
  cross a decision boundary (budget/threshold) — decisiveness filter (6).
- `product_swap`: replace a product id in search results with another
  in-category product id. (No verify tool -> honestly unrecoverable.)
- `stock_plausible`: stock replaced with a plausible count that flips an
  in-stock/out-of-stock or restock decision (e.g. 0 <-> 5).
- `rating_drift`: rating shifted +/-0.3-0.6 to cross the min-rating filter.
  (No verify tool -> honestly unrecoverable.)
- `shipping_drift`: shipping days shifted plausibly to cross a constraint.
  (No verify tool -> honestly unrecoverable.)
- `status_mislabel`: order status swapped to an adjacent status
  (e.g. "shipped" -> "delivered", "delivered" -> "returned").
- `discount_misread`: discount fraction replaced with another real code's
  fraction.

Corruption is STICKY: within an episode, re-calling the exact corrupted
(tool, args) returns the corrupted value again (models the paper's "freeze
recorded tool behavior"). Explicit-failure arm: the same step raises a tool
error on first attempt; the baseline policy retries once and the retry
returns the TRUE value (transient failure — the honest, observable-failure
recovery mechanism).

Per-unit corruption class is sampled from the classes applicable to the
workflow, seeded (see 7).

## 5. Agents (deterministic, fixed-seed)

- `BaselineAgent`: executes the workflow's canonical plan from the frozen
  prefix; trusts tool outputs at face value; NO verification re-queries.
  On explicit tool failure: retry once; on second failure, fall back to the
  prefix-cached value if present, else mark the unit failed. Commits the
  answer computed from observed values.
- `VerifyAgent` (State Checker arm): identical plan, then BEFORE finalizing:
  for each load-bearing observed value (price via get_price, stock via
  get_stock, order status via get_order, discount via check_discount),
  call the corresponding verify tool with the same args; on mismatch,
  replace with the verified value, set `recovered=True` in the trace log,
  and recompute the answer. Extra verification calls are counted and
  reported. Cannot recover product_swap / rating_drift / shipping_drift
  (no verify tool exists) — this bounds recovery below 100% by design and
  mirrors the paper's successive bottlenecks (recognition -> verification
  use -> evidence integration).

## 6. Decisiveness filter (pre-registered calibration)

A silent error that cannot change the answer is not an error. A unit is kept
only if `baseline_answer(corrupted_prefix) != baseline_answer(correct_prefix)`
(verified by running the baseline policy on both prefixes). Up to 25 seeded
resamples per unit slot; if none is decisive, the slot is dropped and the
shortfall is documented (n reported exactly as run).

## 7. Units, seeds, matched design

- n = 167 matched units (~18-19 per workflow), each evaluated under 3
  matched conditions (correct-value / silent-error / explicit-failure) =
  501 instances, mirroring the paper's 167/501 structure.
- Primary experiment seed: 42. Replication seed: 20261022.
- Catalog/unit/corruption sampling all derive from the experiment seed via
  `random.Random(seed)` chains — fully deterministic.
- Bootstrap: paired over the 167 units, B=2000, `numpy`-free pure-python
  implementation, RNG seed 7 (fixed), 95% percentile CI.

## 8. Success criterion

Per-workflow exact-match scorer: the agent's final answer must equal the
ground-truth answer computed from the TRUE world state (correct tool values).
Binary success per instance. Reported as rates; gates use per-unit paired
differences.

## 9. Gate statistics (locked)

- G2a: mean(baseline_correct) >= 0.80.
- G2b: mean(d_s) <= -0.20 with d_s = silent - correct per unit; paired
  bootstrap 95% CI upper bound < 0.
- G2c: mean(d_s) < mean(d_e), d_e = explicit - correct; paired bootstrap
  95% CI of (d_s - d_e) upper bound < 0.
- G3: mean(d_v) >= +0.10 with d_v = verify_silent - baseline_silent;
  paired bootstrap 95% CI lower bound > 0.
- Sanity (non-gating, reported): verify agent on correct-value arm
  (must not degrade clean runs materially); per-class breakdown;
  verification-call cost.

## 10. Deviation policy

Deviations from this protocol are recorded in BUILD_NOTES.md and PAPER.md
under "Deviations", with cause and impact — never silently applied.
