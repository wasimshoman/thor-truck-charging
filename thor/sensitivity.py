"""Sensitivity sweeps around the THOR baseline.

Ported unchanged from explore_sensitivity_and_temporal.ipynb. Each sweep takes the study hexagons
(a DataFrame with MDTN_B_CouSha = daily break-stop demand D and NFCh30m_CouSha = baseline points)
and returns a DataFrame with one column of charging points per tested value, one row per hexagon.
"""
import numpy as np
import pandas as pd
from functools import lru_cache
from . import queueing
from .queueing import MU_30, C_S2, THOR_WQ, THOR_RHO, LAM_FACTOR, lookup, wq_mgc_min

build_table = lru_cache(maxsize=None)(queueing.build_table)  # tables are reused across sweeps

WQ_SCENARIOS = [3, 5, 10, 15, 20, 30]
RHO_SCENARIOS = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.97, 0.99]
CA2_SCENARIOS = [1.0, 1.5, 2.0, 3.0]
MU_SCENARIOS = [1.0, 1.33, 2.0, 3.0, 4.0]          # 1/mu = 60, 45, 30, 20, 15 min (45 min uses 1.33, as in the notebook)
PEAK_SWEEP = [1.0, 1.2, 1.4, 1.44, 1.45, 1.6, 1.666, 1.691, 1.8, 2.0]
PEAK_GRID = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
SWEDEN_PEAK = 1.666
WQ_CAP_MIN = 60.0
TIER_NAMES = ['Saturated', 'Near-saturated', 'Degraded', 'Service OK']


def lam_flat(hexes):
    """Baseline arrival rate (trucks/hour): daily demand x 0.06 (flat over the 16.7-h driving window)."""
    return hexes['MDTN_B_CouSha'] * LAM_FACTOR


def _count(lams, tbl):
    return lams.apply(lambda l: lookup(l, tbl))


def sweep_wq(hexes):
    lam = lam_flat(hexes)
    return pd.DataFrame({f'wq_{w}': _count(lam, build_table(MU_30, w, C_S2, THOR_RHO)) for w in WQ_SCENARIOS})


def sweep_rho(hexes):
    lam = lam_flat(hexes)
    return pd.DataFrame({f'rho_{int(round(r * 100))}': _count(lam, build_table(MU_30, THOR_WQ, C_S2, r))
                         for r in RHO_SCENARIOS})


def sweep_ca2(hexes):
    """Arrival variability: only Ca2 + Cs2 enters Allen-Cunneen, so use cs2_eff = Ca2 + Cs2 - 1."""
    lam = lam_flat(hexes)
    return pd.DataFrame({f'ca2_{str(c).replace(".", "p")}':
                         _count(lam, build_table(MU_30, THOR_WQ, c + C_S2 - 1.0, THOR_RHO)) for c in CA2_SCENARIOS})


def sweep_service_time(hexes):
    lam = lam_flat(hexes)
    return pd.DataFrame({f'svc_{int(round(60 / m))}': _count(lam, build_table(m, THOR_WQ, C_S2, THOR_RHO))
                         for m in MU_SCENARIOS})


def sweep_peak_factor(hexes, peaks=PEAK_SWEEP):
    """Size each hexagon to the peak hour: arrival rate D/24 x p."""
    tbl = build_table(MU_30, THOR_WQ, C_S2, THOR_RHO)
    return pd.DataFrame({f'p_{str(p).replace(".", "p")}': _count(hexes['MDTN_B_CouSha'] * p / 24, tbl)
                         for p in peaks})


def joint_grid_cs2(hexes, cs2_values=(0.0, 1 / 36, 1.0)):
    """Total points for every (Wq, rho_max) pair at three service-variability levels (M/D/c, THOR, exponential service)."""
    lam = lam_flat(hexes)
    rows = []
    for cs2 in cs2_values:
        for w in WQ_SCENARIOS:
            for r in RHO_SCENARIOS:
                rows.append({'Cs2': cs2, 'Wq_min': w, 'rho_max': r,
                             'points': int(_count(lam, build_table(MU_30, w, cs2, r)).sum())})
    return pd.DataFrame(rows)


def summary(counts, base, key):
    """Europe-wide totals and change versus the baseline for one sweep."""
    tot = counts.sum()
    return pd.DataFrame({key: tot.index, 'points': tot.values.astype(int),
                         'delta': (tot.values - base).astype(int),
                         'pct': np.round((tot.values - base) / base * 100, 1)})


def _wq_capped(c, lam):
    if c <= 0:
        return 0.0
    if lam >= c * MU_30:
        return WQ_CAP_MIN
    return min(wq_mgc_min(c, lam), WQ_CAP_MIN)


def busy_hour(hexes, p):
    """Operate the fixed baseline points at peak factor p: per-hexagon lambda, rho, capped wait, tier."""
    lam = hexes['MDTN_B_CouSha'] * p / 24.0
    c = hexes['NFCh30m_CouSha']
    rho = (lam / (c * MU_30)).where(c > 0, 0.0)
    wq = pd.Series([_wq_capped(int(ci), li) for ci, li in zip(c, lam)], index=hexes.index)
    wq_u = pd.Series([wq_mgc_min(int(ci), li) if li < ci * MU_30 else 999.0 for ci, li in zip(c, lam)],
                     index=hexes.index)
    tier = np.select([rho >= 1.0, rho >= 0.95, wq_u > THOR_WQ], TIER_NAMES[:3], default=TIER_NAMES[3])
    return pd.DataFrame({'lambda_busy': lam, 'rho_busy': rho, 'wq_busy_min': wq, 'tier': tier})


def peak_ops(hexes, peaks=PEAK_GRID):
    """Failed share by count and by demand, demand-weighted wait and utilisation (notebook code_peak_ops)."""
    w = hexes['MDTN_B_CouSha']
    rows = []
    for p in peaks:
        b = busy_hour(hexes, p)
        fail = (b['rho_busy'] >= 1.0) | (b['wq_busy_min'] > THOR_WQ)
        rows.append({'peak': p,
                     'failed_pct_count': fail.sum() / len(hexes) * 100,
                     'failed_pct_demand': w[fail].sum() / w.sum() * 100,
                     'wq_dw_min': float((b['wq_busy_min'] * w).sum() / w.sum()),
                     'rho_dw': float((b['rho_busy'].clip(upper=1.0) * w).sum() / w.sum()),
                     'n_saturated': int((b['rho_busy'] >= 1.0).sum())})
    return pd.DataFrame(rows)


def peak_tiers(hexes, base, peaks=PEAK_GRID):
    """Service tiers per peak factor plus extra points needed to restore compliance (code_peak_tiers)."""
    w = hexes['MDTN_B_CouSha']
    tbl = build_table(MU_30, THOR_WQ, C_S2, THOR_RHO)
    rows = []
    for p in peaks:
        b = busy_hour(hexes, p)
        row = {'peak': p}
        for nm in TIER_NAMES:
            m = b['tier'] == nm
            row[f'{nm}_n'] = int(m.sum())
            row[f'{nm}_pct'] = m.sum() / len(hexes) * 100
            row[f'{nm}_dem'] = w[m].sum() / w.sum() * 100
        need = int(_count(w * p / 24, tbl).sum())
        row.update(bays_needed=need, extra_bays=need - base, extra_pct=(need - base) / base * 100)
        rows.append(row)
    return pd.DataFrame(rows)


def country_table(counts, hexes, country, min_points=20):
    """Per-country totals of every sweep column plus the sensitivity indices S_wq and S_rho.

    S = (largest total - smallest total across the sweep) / baseline total, as in notebook cell mg039.
    Countries with fewer than `min_points` baseline points are dropped.
    """
    df = counts.copy()
    df['NFCh30m_CouSha'] = hexes['NFCh30m_CouSha'].values
    df['lambda'] = lam_flat(hexes).values
    df['country'] = np.asarray(country)
    cdf = df.groupby('country').sum().reset_index()
    cdf = cdf[cdf['wq_5'] > 0]
    cdf = cdf[cdf['wq_5'] >= min_points].sort_values('wq_5', ascending=False).reset_index(drop=True)
    wq = [f'wq_{w}' for w in WQ_SCENARIOS]
    rho = [f'rho_{int(round(r * 100))}' for r in RHO_SCENARIOS]
    base = cdf['wq_5'].clip(lower=1)
    cdf['S_wq'] = (cdf[wq].max(axis=1) - cdf[wq].min(axis=1)) / base
    cdf['S_rho'] = (cdf[rho].max(axis=1) - cdf[rho].min(axis=1)) / base
    return cdf
