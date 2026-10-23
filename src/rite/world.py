"""Synthetic e-commerce world + deterministic tool simulator.

ALL data is synthetic (seeded RNG). No real merchant data, no network calls.
Implements the primary toolset and the independent secondary-feed verify
tools, plus sticky silent-error corruption and transient explicit failure
injection for matched-condition evaluation.
"""

import random

CATEGORIES = [
    "smartphones", "laptops", "headphones", "cameras", "tablets",
    "smartwatches", "keyboards", "monitors", "routers", "printers",
    "drones", "consoles",
]

ORDER_STATUSES = ["processing", "shipped", "delivered", "returned"]
# Adjacent-status map for the status_mislabel taxonomy class.
STATUS_ADJACENT = {
    "processing": "shipped",
    "shipped": "delivered",
    "delivered": "returned",
    "returned": "delivered",
}

DISCOUNT_CODES = {
    "SAVE10": 0.10,
    "SAVE15": 0.15,
    "WELCOME20": 0.20,
    "FLASH5": 0.05,
    "MEGA25": 0.25,
    "LOYAL12": 0.12,
}

CARRIERS = ["swiftpost", "quickship", "economail"]


class ToolError(Exception):
    """Explicit tool failure signal (observable by the agent)."""


class Catalog:
    """Seeded synthetic catalog. Deterministic given seed."""

    def __init__(self, seed):
        rng = random.Random(seed ^ 0xCA7A10)
        self.products = {}  # pid -> dict
        self.by_category = {c: [] for c in CATEGORIES}
        self.orders = {}
        n = 0
        for cat in CATEGORIES:
            for i in range(8):
                n += 1
                pid = "P%04d" % n
                price = int(rng.lognormvariate(6.2, 0.9))  # cents-ish scale
                price = max(999, min(price, 199999))
                prod = {
                    "pid": pid,
                    "category": cat,
                    "name": "%s model-%d" % (cat[:-1] if cat.endswith("s") else cat, i + 1),
                    "price_cents": price,
                    "stock": rng.choice([0, 0, 1, 2, 3, 5, 8, 12, 20, 35, 50]),
                    "rating": round(rng.uniform(3.0, 5.0), 1),
                    "ship_days": rng.choice([1, 2, 2, 3, 3, 4, 5, 7]),
                    "sellers": [],
                }
                for s in range(rng.choice([1, 2, 2, 3])):
                    prod["sellers"].append((
                        "S%04d" % (n * 10 + s),
                        round(rng.uniform(3.5, 5.0), 1),
                        rng.choice([12, 45, 120, 340, 890, 2100]),
                    ))
                self.products[pid] = prod
                self.by_category[cat].append(pid)
        for i in range(60):
            oid = "O%04d" % (i + 1)
            status = rng.choice(ORDER_STATUSES)
            self.orders[oid] = {
                "oid": oid,
                "status": status,
                "eta_days": rng.choice([0, 1, 2, 3, 5, 7]),
                "total_cents": int(rng.lognormvariate(8.5, 0.8)),
                "days_since": rng.choice([1, 3, 5, 9, 14, 21, 30]),
            }


def _true_value(catalog, tool, args):
    """Ground-truth tool outputs from the synthetic world."""
    if tool == "search_products":
        category, max_price = args
        out = [pid for pid in catalog.by_category[category]
               if max_price is None or catalog.products[pid]["price_cents"] <= max_price]
        return sorted(out)
    if tool == "get_price":
        return catalog.products[args[0]]["price_cents"]
    if tool == "get_stock":
        return catalog.products[args[0]]["stock"]
    if tool == "get_rating":
        return catalog.products[args[0]]["rating"]
    if tool == "get_shipping_days":
        return catalog.products[args[0]]["ship_days"]
    if tool == "get_category":
        return catalog.products[args[0]]["category"]
    if tool == "check_discount":
        return DISCOUNT_CODES.get(args[0], 0.0)
    if tool == "get_order":
        return dict(catalog.orders[args[0]])
    if tool == "get_seller":
        return [tuple(s) for s in catalog.products[args[0]]["sellers"]]
    if tool == "get_shipping_quote":
        pid, dest = args
        base = catalog.products[pid]["ship_days"]
        return [(c, 299 + base * 149 + (abs(hash(c + dest)) % 200)) for c in CARRIERS]
    # ---- secondary-feed verify tools (independent channel, never corrupted)
    if tool == "verify_price":
        return catalog.products[args[0]]["price_cents"]
    if tool == "verify_stock":
        return catalog.products[args[0]]["stock"]
    if tool == "verify_order_status":
        return catalog.orders[args[0]]["status"]
    if tool == "verify_discount":
        return DISCOUNT_CODES.get(args[0], 0.0)
    raise ValueError("unknown tool: %s" % tool)


class ToolView:
    """An agent's view of the tools for one episode/condition.

    corrupt: None | {"tool": name, "args": tuple, "kind": "silent"|"explicit",
                     "value": corrupted_value}
    - silent: the corrupted (tool, args) returns the corrupted value on EVERY
      call (sticky — models frozen recorded behavior).
    - explicit: the corrupted (tool, args) raises ToolError on the FIRST call
      only; retries return the true value (transient, observable failure).
    Verify tools always return true values (independent secondary feed).
    Every call is appended to self.trace as (tool, args, observed, failed).
    """

    VERIFY_TOOLS = {"verify_price", "verify_stock", "verify_order_status",
                    "verify_discount"}

    def __init__(self, catalog, corrupt=None):
        self.catalog = catalog
        self.corrupt = corrupt
        self.trace = []
        self._attempts = {}

    def call(self, tool, *args):
        key = (tool, tuple(args))
        if tool in self.VERIFY_TOOLS:
            val = _true_value(self.catalog, tool, tuple(args))
            self.trace.append((tool, tuple(args), val, False))
            return val
        c = self.corrupt
        if c is not None and c["tool"] == tool and tuple(c["args"]) == tuple(args):
            if c["kind"] == "silent":
                self.trace.append((tool, tuple(args), c["value"], False))
                return c["value"]
            # explicit: fail once, then recover to the true value
            n = self._attempts.get(key, 0)
            self._attempts[key] = n + 1
            if n == 0:
                self.trace.append((tool, tuple(args), None, True))
                raise ToolError("tool %s failed (explicit)" % tool)
        val = _true_value(self.catalog, tool, tuple(args))
        self.trace.append((tool, tuple(args), val, False))
        return val

    # ---- primary tool convenience wrappers ----
    def search_products(self, category, max_price=None):
        return self.call("search_products", category, max_price)

    def get_price(self, pid):
        return self.call("get_price", pid)

    def get_stock(self, pid):
        return self.call("get_stock", pid)

    def get_rating(self, pid):
        return self.call("get_rating", pid)

    def get_shipping_days(self, pid):
        return self.call("get_shipping_days", pid)

    def get_category(self, pid):
        return self.call("get_category", pid)

    def check_discount(self, code):
        return self.call("check_discount", code)

    def get_order(self, oid):
        return self.call("get_order", oid)

    def get_seller(self, pid):
        return self.call("get_seller", pid)

    def get_shipping_quote(self, pid, dest):
        return self.call("get_shipping_quote", pid, dest)

    # ---- verify tool wrappers (independent feed) ----
    def verify_price(self, pid):
        return self.call("verify_price", pid)

    def verify_stock(self, pid):
        return self.call("verify_stock", pid)

    def verify_order_status(self, oid):
        return self.call("verify_order_status", oid)

    def verify_discount(self, code):
        return self.call("verify_discount", code)
