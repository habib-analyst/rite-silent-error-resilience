"""Deterministic scripted agents.

BaselineAgent: executes the workflow's canonical plan, trusts tool outputs
at face value, performs NO verification re-queries. On an explicit tool
failure it retries the call once (pre-registered observable-failure
recovery); a second consecutive failure marks the episode failed.

VerifyAgent (State Checker arm): identical plan, then BEFORE finalizing it
re-queries each load-bearing observed value through the INDEPENDENT
secondary-feed verify tools (verify_price / verify_stock /
verify_order_status / verify_discount). On mismatch it replaces the value,
flags recovered=True, and recomputes the answer. Corruption is sticky on the
corrupted (tool, args) pair, so same-tool re-query cannot recover — recovery
must come from the independent path. Classes without a verify tool
(product_swap, rating_drift, shipping_drift) are honestly unrecoverable.
"""

from .world import ToolError


class AgentFailed(Exception):
    pass


class _RetryingView:
    """Wraps a ToolView with the pre-registered retry-once policy."""

    def __init__(self, view):
        self._view = view

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        fn = getattr(self._view, name)

        def _call(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ToolError:
                try:
                    return fn(*args, **kwargs)  # one retry
                except ToolError:
                    raise AgentFailed("tool %s failed twice" % name)

        return _call


# (tool observed) -> (verify tool, arg projection, value projection,
#                      replacement merger)
def _verify_plan(obs_key, obs_val):
    tool, args = obs_key
    if tool == "get_price":
        return ("verify_price", args, obs_val,
                lambda new, old: new)
    if tool == "get_stock":
        return ("verify_stock", args, obs_val,
                lambda new, old: new)
    if tool == "get_order":
        return ("verify_order_status", args, obs_val["status"],
                lambda new, old: dict(old, status=new))
    if tool == "check_discount":
        return ("verify_discount", args, obs_val,
                lambda new, old: new)
    return None


class BaselineAgent:
    name = "baseline"

    def run(self, workflow, view, params):
        rview = _RetryingView(view)
        try:
            answer, obs = workflow.run(rview, params)
        except AgentFailed:
            return None, False
        return answer, True


class VerifyAgent:
    """Baseline plan + pre-finalization verification pass (State Checker)."""
    name = "verify"

    def run(self, workflow, view, params):
        rview = _RetryingView(view)
        try:
            answer, obs = workflow.run(rview, params)
        except AgentFailed:
            return None, False, False, 0
        obs = dict(obs)
        recovered = False
        n_verify = 0
        for key, val in list(obs.items()):
            plan = _verify_plan(key, val)
            if plan is None:
                continue
            vtool, vargs, observed_v, merge = plan
            n_verify += 1
            verified = getattr(view, vtool)(*vargs)  # independent feed
            if verified != observed_v:
                obs[key] = merge(verified, val)
                recovered = True
        answer2 = workflow.answer(params, obs)
        return answer2, True, recovered, n_verify
