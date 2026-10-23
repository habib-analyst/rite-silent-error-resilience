"""Paired bootstrap statistics (pure python, fixed seeds)."""


def paired_bootstrap_ci(diffs, B=2000, seed=7, alpha=0.05):
    """95% percentile CI for the mean of per-unit paired differences.

    Returns (mean, lo, hi). Deterministic given seed.
    """
    import random
    rng = random.Random(seed)
    n = len(diffs)
    if n == 0:
        raise ValueError("empty diffs")
    mean = sum(diffs) / n
    boots = []
    for _ in range(B):
        s = 0.0
        for _ in range(n):
            s += diffs[rng.randrange(n)]
        boots.append(s / n)
    boots.sort()
    lo = boots[int((alpha / 2) * B)]
    hi = boots[int((1 - alpha / 2) * B) - 1]
    return mean, lo, hi
