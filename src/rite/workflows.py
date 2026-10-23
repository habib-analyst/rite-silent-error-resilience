"""Nine synthetic e-commerce workflows.

Each workflow defines: param generation, the agent's canonical plan
(run -> (answer, obs)), a pure answer() recompute from observed values
(used by the verification-path agent), ground_truth() from the true world,
and make_corrupt_spec() which builds the injected silent-error value for a
sampled taxonomy class at the first plan step whose output matches it.

obs: dict mapping (tool, args_tuple) -> observed value for load-bearing
values. The verify agent corrects obs through the independent verify tools
and recomputes answer() — this is the State Checker analog.
"""

from .world import ToolView, STATUS_ADJACENT, DISCOUNT_CODES


def rec(view, obs, tool, *args):
    """Call a tool through the view, recording load-bearing values in obs."""
    val = getattr(view, tool)(*args)
    obs[(tool, tuple(args))] = val
    return val


class _W:
    name = "base"
    applicable = []

    def generate(self, rng, catalog):
        raise NotImplementedError

    def run(self, view, params):
        raise NotImplementedError

    def answer(self, params, obs):
        raise NotImplementedError

    def ground_truth(self, catalog, params):
        view = ToolView(catalog)
        return self.run(view, params)[0]

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        raise NotImplementedError


def _drifted(true_price, delta):
    """Plausible drifted price guaranteed to differ from the true price."""
    val = max(999, int(true_price * (1.0 + delta)))
    if val == true_price:
        val = true_price + 137  # nudge off the clamp floor, stays plausible
    return val


# ---------------------------------------------------------------- W1
class CheapestInStock(_W):
    name = "cheapest_in_stock"
    applicable = ["price_swap", "price_drift", "product_swap",
                  "stock_plausible", "rating_drift", "shipping_drift",
                  "discount_misread"]

    def generate(self, rng, catalog):
        cat = rng.choice(list(catalog.by_category.keys()))
        return {
            "category": cat,
            "budget_cents": rng.choice([30000, 50000, 80000, 120000]),
            "min_rating": rng.choice([3.5, 4.0, 4.5]),
            "code": rng.choice(list(DISCOUNT_CODES.keys())),
            "max_ship_days": rng.choice([3, 5, 7]),
        }

    def run(self, view, params):
        obs = {}
        pids = rec(view, obs, "search_products", params["category"], None)
        for pid in pids:
            rec(view, obs, "get_price", pid)
            rec(view, obs, "get_stock", pid)
            rec(view, obs, "get_rating", pid)
            rec(view, obs, "get_shipping_days", pid)
        rec(view, obs, "check_discount", params["code"])
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        pids = obs[("search_products", (params["category"], None))]
        disc = obs[("check_discount", (params["code"],))]
        best = None
        for pid in pids:
            price = obs[("get_price", (pid,))]
            stock = obs[("get_stock", (pid,))]
            rating = obs[("get_rating", (pid,))]
            ship = obs[("get_shipping_days", (pid,))]
            if price <= params["budget_cents"] and stock > 0 \
               and rating >= params["min_rating"] and ship <= params["max_ship_days"]:
                if best is None or (price, pid) < (best[1], best[0]):
                    best = (pid, price)
        if best is None:
            return ("NONE", 0)
        total = int(round(best[1] * (1.0 - disc)))
        return (best[0], total)

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        view = ToolView(catalog)
        pids = view.search_products(params["category"], None)
        pid = pids[0]
        true_price = catalog.products[pid]["price_cents"]
        if corr_class == "price_swap":
            others = [p for p in pids[1:]
                      if catalog.products[p]["price_cents"] != true_price]
            other = rng.choice(others)
            return {"tool": "get_price", "args": (pid,),
                    "value": catalog.products[other]["price_cents"]}
        if corr_class == "price_drift":
            delta = rng.choice([-0.12, -0.08, 0.08, 0.12])
            return {"tool": "get_price", "args": (pid,),
                    "value": _drifted(true_price, delta)}
        if corr_class == "product_swap":
            pool = [p for p in catalog.by_category[params["category"]] if p not in pids]
            if not pool:
                pool = [p for p in pids[1:]]
            swap = rng.choice(pool)
            val = [swap if p == pid else p for p in pids]
            return {"tool": "search_products", "args": (params["category"], None),
                    "value": val}
        if corr_class == "stock_plausible":
            true_stock = catalog.products[pid]["stock"]
            val = 0 if true_stock > 0 else 5
            return {"tool": "get_stock", "args": (pid,), "value": val}
        if corr_class == "rating_drift":
            true_r = catalog.products[pid]["rating"]
            mr = params["min_rating"]
            val = round(mr - 0.5, 1) if true_r >= mr else round(min(5.0, mr + 0.5), 1)
            return {"tool": "get_rating", "args": (pid,), "value": val}
        if corr_class == "shipping_drift":
            true_s = catalog.products[pid]["ship_days"]
            mx = params["max_ship_days"]
            val = mx + 2 if true_s <= mx else max(1, mx - 1)
            return {"tool": "get_shipping_days", "args": (pid,), "value": val}
        if corr_class == "discount_misread":
            true_d = DISCOUNT_CODES[params["code"]]
            alt = rng.choice([d for d in DISCOUNT_CODES.values() if d != true_d])
            return {"tool": "check_discount", "args": (params["code"],),
                    "value": alt}
        raise ValueError(corr_class)


# ---------------------------------------------------------------- W2
class OrderLookup(_W):
    name = "order_lookup"
    applicable = ["status_mislabel"]

    def generate(self, rng, catalog):
        return {"oid": rng.choice(list(catalog.orders.keys()))}

    def run(self, view, params):
        obs = {}
        order = rec(view, obs, "get_order", params["oid"])
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        order = obs[("get_order", (params["oid"],))]
        return (order["status"], order["eta_days"])

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        assert corr_class == "status_mislabel"
        true = dict(catalog.orders[params["oid"]])
        val = dict(true)
        val["status"] = STATUS_ADJACENT[true["status"]]
        return {"tool": "get_order", "args": (params["oid"],), "value": val}


# ---------------------------------------------------------------- W3
class RefundCheck(_W):
    name = "refund_check"
    applicable = ["status_mislabel"]

    def generate(self, rng, catalog):
        return {"oid": rng.choice(list(catalog.orders.keys())),
                "policy_days": rng.choice([7, 14, 30])}

    def run(self, view, params):
        obs = {}
        rec(view, obs, "get_order", params["oid"])
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        order = obs[("get_order", (params["oid"],))]
        elig = order["status"] == "delivered" and order["days_since"] <= params["policy_days"]
        return (bool(elig), order["total_cents"] if elig else 0)

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        assert corr_class == "status_mislabel"
        true = dict(catalog.orders[params["oid"]])
        val = dict(true)
        val["status"] = STATUS_ADJACENT[true["status"]]
        return {"tool": "get_order", "args": (params["oid"],), "value": val}


# ---------------------------------------------------------------- W4
class BundleTotal(_W):
    name = "bundle_total"
    applicable = ["price_swap", "price_drift", "discount_misread"]

    def generate(self, rng, catalog):
        cat = rng.choice(list(catalog.by_category.keys()))
        pids = rng.sample(catalog.by_category[cat], 3)
        return {"pids": pids, "code": rng.choice(list(DISCOUNT_CODES.keys()))}

    def run(self, view, params):
        obs = {}
        for pid in params["pids"]:
            rec(view, obs, "get_price", pid)
        rec(view, obs, "check_discount", params["code"])
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        disc = obs[("check_discount", (params["code"],))]
        subtotal = sum(obs[("get_price", (pid,))] for pid in params["pids"])
        return int(round(subtotal * (1.0 - disc)))

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        pid = params["pids"][0]
        true_price = catalog.products[pid]["price_cents"]
        if corr_class == "price_swap":
            cat = catalog.products[pid]["category"]
            others = [p for p in catalog.by_category[cat]
                      if catalog.products[p]["price_cents"] != true_price]
            other = rng.choice(others)
            return {"tool": "get_price", "args": (pid,),
                    "value": catalog.products[other]["price_cents"]}
        if corr_class == "price_drift":
            delta = rng.choice([-0.12, -0.08, 0.08, 0.12])
            return {"tool": "get_price", "args": (pid,),
                    "value": _drifted(true_price, delta)}
        if corr_class == "discount_misread":
            true_d = DISCOUNT_CODES[params["code"]]
            alt = rng.choice([d for d in DISCOUNT_CODES.values() if d != true_d])
            return {"tool": "check_discount", "args": (params["code"],),
                    "value": alt}
        raise ValueError(corr_class)


# ---------------------------------------------------------------- W5
class RestockList(_W):
    name = "restock_list"
    applicable = ["stock_plausible", "product_swap"]

    def generate(self, rng, catalog):
        return {"category": rng.choice(list(catalog.by_category.keys())),
                "threshold": rng.choice([3, 6, 10])}

    def run(self, view, params):
        obs = {}
        pids = rec(view, obs, "search_products", params["category"], None)
        for pid in pids:
            rec(view, obs, "get_stock", pid)
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        pids = obs[("search_products", (params["category"], None))]
        out = [pid for pid in pids
               if obs.get(("get_stock", (pid,)), 0) < params["threshold"]]
        return tuple(sorted(out))

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        view = ToolView(catalog)
        pids = view.search_products(params["category"], None)
        pid = pids[0]
        if corr_class == "stock_plausible":
            true_stock = catalog.products[pid]["stock"]
            th = params["threshold"]
            # flip across the threshold, plausibly
            val = 0 if true_stock >= th else th + 2
            return {"tool": "get_stock", "args": (pid,), "value": val}
        if corr_class == "product_swap":
            pool = [p for p in catalog.by_category[params["category"]] if p not in pids]
            if not pool:
                pool = [p for p in pids[1:]]
            swap = rng.choice(pool)
            val = [swap if p == pid else p for p in pids]
            return {"tool": "search_products", "args": (params["category"], None),
                    "value": val}
        raise ValueError(corr_class)


# ---------------------------------------------------------------- W6
class ShipQuote(_W):
    name = "ship_quote"
    applicable = ["price_swap"]  # applied to quote cost: in-distribution
    # cost substitution from the same quote list (same semantic class).

    def generate(self, rng, catalog):
        cat = rng.choice(list(catalog.by_category.keys()))
        return {"pid": rng.choice(catalog.by_category[cat]),
                "dest": rng.choice(["berlin", "london", "paris", "madrid"])}

    def run(self, view, params):
        obs = {}
        quotes = rec(view, obs, "get_shipping_quote", params["pid"], params["dest"])
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        quotes = obs[("get_shipping_quote", (params["pid"], params["dest"]))]
        best = min(quotes, key=lambda q: (q[1], q[0]))
        return (best[0], best[1])

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        assert corr_class == "price_swap"
        view = ToolView(catalog)
        quotes = view.get_shipping_quote(params["pid"], params["dest"])
        costs = sorted(set(q[1] for q in quotes))
        # replace the cheapest option's cost with another real cost from
        # the same quote list (plausible-but-wrong, in-distribution)
        cheapest = min(quotes, key=lambda q: (q[1], q[0]))
        alt = rng.choice([c for c in costs if c != cheapest[1]])
        val = [(c, alt if (c, co) == (cheapest[0], cheapest[1]) else co)
               for (c, co) in quotes]
        return {"tool": "get_shipping_quote",
                "args": (params["pid"], params["dest"]), "value": val}


# ---------------------------------------------------------------- W7
class PriceAudit(_W):
    name = "price_audit"
    applicable = ["price_swap", "price_drift"]

    def generate(self, rng, catalog):
        return {"category": rng.choice(list(catalog.by_category.keys())),
                "tol": 0.30}

    def run(self, view, params):
        obs = {}
        pids = rec(view, obs, "search_products", params["category"], None)
        for pid in pids:
            rec(view, obs, "get_price", pid)
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        pids = obs[("search_products", (params["category"], None))]
        prices = [obs[("get_price", (pid,))] for pid in pids]
        med = sorted(prices)[len(prices) // 2]
        flagged = [pid for pid in pids
                   if abs(obs[("get_price", (pid,))] - med) / med > params["tol"]]
        return tuple(sorted(flagged))

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        view = ToolView(catalog)
        pids = view.search_products(params["category"], None)
        pid = pids[0]
        true_price = catalog.products[pid]["price_cents"]
        if corr_class == "price_swap":
            others = [p for p in pids[1:]
                      if catalog.products[p]["price_cents"] != true_price]
            other = rng.choice(others)
            return {"tool": "get_price", "args": (pid,),
                    "value": catalog.products[other]["price_cents"]}
        if corr_class == "price_drift":
            delta = rng.choice([-0.35, 0.35])  # cross the 30% audit band
            return {"tool": "get_price", "args": (pid,),
                    "value": _drifted(true_price, delta)}
        raise ValueError(corr_class)


# ---------------------------------------------------------------- W8
class CouponBest(_W):
    name = "coupon_best"
    applicable = ["price_swap", "price_drift", "discount_misread"]

    def generate(self, rng, catalog):
        cat = rng.choice(list(catalog.by_category.keys()))
        return {"pids": rng.sample(catalog.by_category[cat], 3),
                "codes": rng.sample(list(DISCOUNT_CODES.keys()), 3)}

    def run(self, view, params):
        obs = {}
        for pid in params["pids"]:
            rec(view, obs, "get_price", pid)
        for code in params["codes"]:
            rec(view, obs, "check_discount", code)
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        subtotal = sum(obs[("get_price", (pid,))] for pid in params["pids"])
        scored = []
        for code in params["codes"]:
            d = obs[("check_discount", (code,))]
            scored.append((int(round(subtotal * (1.0 - d))), code))
        best_total, best_code = min(scored, key=lambda t: (t[0], t[1]))
        return (best_code, best_total)

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        if corr_class in ("price_swap", "price_drift"):
            pid = params["pids"][0]
            true_price = catalog.products[pid]["price_cents"]
            if corr_class == "price_swap":
                cat = catalog.products[pid]["category"]
                others = [p for p in catalog.by_category[cat]
                          if catalog.products[p]["price_cents"] != true_price]
                other = rng.choice(others)
                val = catalog.products[other]["price_cents"]
            else:
                delta = rng.choice([-0.12, -0.08, 0.08, 0.12])
                val = _drifted(true_price, delta)
            return {"tool": "get_price", "args": (pid,), "value": val}
        if corr_class == "discount_misread":
            code = params["codes"][0]
            true_d = DISCOUNT_CODES[code]
            alt = rng.choice([d for d in DISCOUNT_CODES.values() if d != true_d])
            return {"tool": "check_discount", "args": (code,), "value": alt}
        raise ValueError(corr_class)


# ---------------------------------------------------------------- W9
class TopSeller(_W):
    name = "top_seller"
    applicable = ["rating_drift"]  # applied to seller rating: another real
    # seller rating from the same product (same semantic class).

    def generate(self, rng, catalog):
        cat = rng.choice(list(catalog.by_category.keys()))
        return {"pid": rng.choice(catalog.by_category[cat]),
                "min_sales": rng.choice([50, 200, 500])}

    def run(self, view, params):
        obs = {}
        rec(view, obs, "get_seller", params["pid"])
        return self.answer(params, obs), obs

    def answer(self, params, obs):
        sellers = obs[("get_seller", (params["pid"],))]
        cands = [s for s in sellers if s[2] >= params["min_sales"]]
        if not cands:
            return ("NONE",)
        best = max(cands, key=lambda s: (s[1], s[2], s[0]))
        return (best[0],)

    def make_corrupt_spec(self, catalog, params, corr_class, rng):
        assert corr_class == "rating_drift"
        view = ToolView(catalog)
        sellers = view.get_seller(params["pid"])
        ratings = sorted(set(s[1] for s in sellers))
        if len(ratings) < 2:
            # fall back: nudge within plausible band (still in-distribution)
            ratings = [sellers[0][1], round(sellers[0][1] - 0.5, 1)]
        # corrupt the current winner's rating downward to a real rating
        winner = max(sellers, key=lambda s: (s[1], s[2], s[0]))
        alt = rng.choice([r for r in ratings if r != winner[1]])
        val = [(s[0], alt if s[0] == winner[0] else s[1], s[2]) for s in sellers]
        return {"tool": "get_seller", "args": (params["pid"],), "value": val}


WORKFLOWS = [CheapestInStock(), OrderLookup(), RefundCheck(), BundleTotal(),
             RestockList(), ShipQuote(), PriceAudit(), CouponBest(),
             TopSeller()]
WORKFLOW_BY_NAME = {w.name: w for w in WORKFLOWS}
