"""Silent-error taxonomy: fixed class inventory + plausibility checks.

The 8 semantic classes (locked in PREREG.md). Injected values must be
plausible-but-wrong: same schema, in-distribution (drawn from the catalog),
never out-of-range garbage. The validators below are used by the test suite
to enforce that property on every generated corruption spec.
"""

TAXONOMY = [
    "price_swap",       # another real in-category price
    "price_drift",      # realistic +/- delta crossing a decision boundary
    "product_swap",     # another real in-category product id
    "stock_plausible",  # plausible count flipping an in-stock/restock decision
    "rating_drift",     # realistic shift crossing a rating filter
    "shipping_drift",   # plausible shift crossing a shipping constraint
    "status_mislabel",  # adjacent order status
    "discount_misread",  # another real discount code's fraction
]

# Classes a verify tool exists for (independent secondary feed) -> the State
# Checker arm can recover them. The rest bound recovery below 100% by design.
RECOVERABLE = {"price_swap", "price_drift", "stock_plausible",
               "status_mislabel", "discount_misread"}
UNRECOVERABLE = {"product_swap", "rating_drift", "shipping_drift"}
assert set(TAXONOMY) == RECOVERABLE | UNRECOVERABLE


def check_plausible(corr_class, tool, args, value, true_value):
    """Assert the corrupted value is plausible-but-wrong.

    Raises AssertionError on violation. Used by tests on generated specs.
    """
    assert value != true_value, "corruption must change the value"
    if corr_class in ("price_swap", "price_drift"):
        if tool == "get_shipping_quote":
            # W6 application: in-distribution quote-cost substitution; the
            # corrupted value is the full quote list with one real cost
            # swapped in (same semantic class, composite form).
            assert isinstance(value, list) and all(
                isinstance(c, str) and isinstance(co, int)
                and 100 <= co <= 5000 for c, co in value), \
                "quote costs must stay plausible, got %r" % (value,)
            return
        assert isinstance(value, int) and 999 <= value <= 199999, \
            "price must stay in catalog range, got %r" % (value,)
    elif corr_class == "product_swap":
        assert isinstance(value, list) and all(
            isinstance(p, str) and p.startswith("P") for p in value), \
            "swapped search output must be a list of product ids"
        assert sorted(value) != sorted(true_value), "product set must change"
    elif corr_class == "stock_plausible":
        assert isinstance(value, int) and 0 <= value <= 60, \
            "stock must stay plausible, got %r" % (value,)
    elif corr_class == "rating_drift":
        if tool == "get_seller":
            # W9 application: another real seller rating from the same
            # product (same semantic class, composite form).
            assert isinstance(value, list) and all(
                isinstance(s[0], str) and 3.5 <= s[1] <= 5.0
                for s in value), \
                "seller ratings must stay plausible, got %r" % (value,)
            return
        assert isinstance(value, float) and 3.0 <= value <= 5.0, \
            "rating must stay in catalog range, got %r" % (value,)
    elif corr_class == "shipping_drift":
        assert isinstance(value, int) and 1 <= value <= 9, \
            "ship days must stay plausible, got %r" % (value,)
    elif corr_class == "status_mislabel":
        from .world import ORDER_STATUSES
        assert isinstance(value, dict) and value["status"] in ORDER_STATUSES, \
            "status must be a real status"
        assert value["status"] != true_value["status"]
    elif corr_class == "discount_misread":
        from .world import DISCOUNT_CODES
        assert value in DISCOUNT_CODES.values(), \
            "discount must be a real code fraction"
    else:
        raise ValueError("unknown class %s" % corr_class)
