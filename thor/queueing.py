"""M/G/c waiting time (Allen-Cunneen) and charging-point sizing.

Ported unchanged from explore_sensitivity_and_temporal.ipynb (cell mg007).
"""
import math
import numpy as np
import pandas as pd

MU_30 = 2.0          # trucks per hour one 30-minute charging point serves
C_S2 = 1 / 36        # squared coefficient of variation of service time (30 +/- 5 min)
THOR_WQ = 5          # baseline waiting-time standard (minutes)
THOR_RHO = 0.95      # baseline utilisation cap
LAM_FACTOR = 0.06    # trucks/day -> trucks/hour over the 16.7-h driving window (kept exactly 0.06)
C_MAX = 120


def erlang_c(c, a):
    """Probability that an arriving truck waits, M/M/c, computed in log space."""
    c = int(c)
    rho = a / c
    if rho >= 1.0:
        return 1.0
    log_a = math.log(a) if a > 0 else -math.inf
    log_terms = [0.0]
    for k in range(1, c):
        log_terms.append(log_terms[-1] + log_a - math.log(k))
    log_last = log_terms[-1] + log_a - math.log(c) - math.log(1.0 - rho)
    max_log = max(max(log_terms), log_last)
    denom = sum(math.exp(t - max_log) for t in log_terms) + math.exp(log_last - max_log)
    return math.exp(log_last - max_log) / denom


def wq_mmc(c, lam, mu):
    """M/M/c expected waiting time in hours."""
    c = int(c)
    a = lam / mu
    if a / c >= 1.0:
        return math.inf
    return erlang_c(c, a) / (c * mu - lam)


def wq_mgc(c, lam, mu, c_s2):
    """Allen-Cunneen M/G/c waiting time in hours, Poisson arrivals (Ca2 = 1)."""
    return wq_mmc(c, lam, mu) * (1 + c_s2) / 2


def wq_mgc_min(c, lam, mu=MU_30, cs2=C_S2):
    """Allen-Cunneen M/G/c waiting time in minutes; inf if saturated."""
    if c <= 0 or lam <= 0:
        return 0.0
    if lam / (c * mu) >= 1.0:
        return np.inf
    return wq_mgc(c, lam, mu, cs2) * 60


def bisect_lam(c, mu, target_hr, tol=1e-8):
    """Arrival rate at which the M/M/c waiting time equals target_hr."""
    lo, hi = 1e-9, c * mu * (1.0 - 1e-9)
    if wq_mmc(c, lo, mu) > target_hr:
        return 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if (hi - lo) < tol:
            return mid
        if wq_mmc(c, mid, mu) <= target_hr:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def build_table(mu, wq_target_min, c_s2, rho_max, c_max=C_MAX):
    """Largest admissible arrival rate for each point count c = 1..c_max.

    c_s2 is the effective variability: for arrival variability Ca2 pass Ca2 + Cs2 - 1.
    """
    target_hr = (wq_target_min / 60.0) / ((1 + c_s2) / 2.0)
    rows = []
    for c in range(1, c_max + 1):
        lam_wq = bisect_lam(c, mu, target_hr)
        lam_cap = rho_max * c * mu
        rows.append({'servers': c, 'lambda': round(min(lam_wq, lam_cap), 6),
                     'lam_wq': round(lam_wq, 6), 'lam_cap': round(lam_cap, 6),
                     'wq_binds': (lam_wq <= lam_cap)})
    return pd.DataFrame(rows)


def lookup(lam, tbl, c_max=C_MAX):
    """Smallest point count whose table entry exceeds lam (0 if lam <= 0)."""
    if lam <= 0:
        return 0
    m = tbl[tbl['lambda'] > lam]
    if not m.empty:
        return int(m.iloc[0]['servers'])
    # ponytail: linear tiling beyond the table; never reached in any sweep here (max need 57 points)
    lam_max = tbl['lambda'].iloc[-1]
    whole = int(lam // lam_max)
    tail = tbl[tbl['lambda'] > lam % lam_max]
    extra = int(tail.iloc[0]['servers']) if not tail.empty else 0
    return int(c_max * whole + extra)


def size(lam, wq=THOR_WQ, rho_max=THOR_RHO, cs2=C_S2, ca2=1.0, mu=MU_30):
    """Charging points c*(lambda; Wq, rho_max, Cs2, Ca2, 1/mu) for one arrival rate."""
    return lookup(lam, build_table(mu, wq, ca2 + cs2 - 1.0, rho_max))


if __name__ == '__main__':
    t = build_table(MU_30, THOR_WQ, C_S2, THOR_RHO)
    assert lookup(0.0, t) == 0 and lookup(0.05, t) == 1
    assert size(1.0) == lookup(1.0, t)
    assert abs(wq_mgc_min(5, 6.0) - wq_mmc(5, 6.0, MU_30) * 60 * (1 + C_S2) / 2) < 1e-9
    print('queueing self-check OK')
