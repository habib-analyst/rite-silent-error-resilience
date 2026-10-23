"""Kill-gate evaluation from experiment records (locked bars)."""

from .stats import paired_bootstrap_ci

B = 2000
BOOT_SEED = 7


def evaluate_gates(records):
    n = len(records)
    bc = [r["baseline_correct"] for r in records]
    bs = [r["baseline_silent"] for r in records]
    be = [r["baseline_explicit"] for r in records]
    vs = [r["verify_silent"] for r in records]
    vc = [r["verify_correct"] for r in records]

    d_silent = [s - c for s, c in zip(bs, bc)]       # silent - correct
    d_explicit = [e - c for e, c in zip(be, bc)]     # explicit - correct
    d_recov = [v - s for v, s in zip(vs, bs)]        # verify - baseline (silent)
    d_s_vs_e = [a - b for a, b in zip(d_silent, d_explicit)]

    g2a_rate = sum(bc) / n
    m_s, lo_s, hi_s = paired_bootstrap_ci(d_silent, B=B, seed=BOOT_SEED)
    m_e, lo_e, hi_e = paired_bootstrap_ci(d_explicit, B=B, seed=BOOT_SEED)
    m_se, lo_se, hi_se = paired_bootstrap_ci(d_s_vs_e, B=B, seed=BOOT_SEED)
    m_r, lo_r, hi_r = paired_bootstrap_ci(d_recov, B=B, seed=BOOT_SEED)

    g2a = g2a_rate >= 0.80
    g2b = (m_s <= -0.20) and (hi_s < 0)
    g2c = (m_s < m_e) and (hi_se < 0)
    g3 = (m_r >= 0.10) and (lo_r > 0)

    return {
        "n": n,
        "baseline_correct_rate": g2a_rate,
        "baseline_silent_rate": sum(bs) / n,
        "baseline_explicit_rate": sum(be) / n,
        "verify_silent_rate": sum(vs) / n,
        "verify_correct_rate": sum(vc) / n,
        "mean_verify_calls": sum(r["verify_calls"] for r in records) / n,
        "recovery_flag_rate": sum(r["verify_recovered_flag"]
                                   for r in records) / n,
        "g2a": {"pass": bool(g2a), "rate": g2a_rate, "bar": 0.80},
        "g2b": {"pass": bool(g2b), "mean_drop_pp": m_s * 100,
                "ci_pp": [lo_s * 100, hi_s * 100], "bar_pp": -20},
        "g2c": {"pass": bool(g2c),
                "mean_silent_drop_pp": m_s * 100,
                "mean_explicit_drop_pp": m_e * 100,
                "diff_ci_pp": [lo_se * 100, hi_se * 100]},
        "g3": {"pass": bool(g3), "mean_recovery_pp": m_r * 100,
               "ci_pp": [lo_r * 100, hi_r * 100], "bar_pp": 10},
        "verdict": "PASS" if (g2a and g2b and g2c and g3) else "KILL",
    }
