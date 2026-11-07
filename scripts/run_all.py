"""Run every sweep, write results/, and print a PASS/FAIL table against the paper and the notebook outputs.

Usage: python scripts/run_all.py
"""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from thor import sensitivity as S                      # noqa: E402
from thor.data import load_study_area, require, HEX_FILE, COUNTRY_FILE, EXCLUDE_COUNTRIES   # noqa: E402

RES = ROOT / 'results'
CSV = RES / 'csv'
REF = ROOT / 'data' / 'reference'
CSV.mkdir(parents=True, exist_ok=True)

# Names (paper Appendix D, three corrected by coordinates) for the seven hexagons that saturate at the Swedish peak.
SATURATED_NAMES = {
    '851948abfffffff': 'Calais (France)',
    '85195107fffffff': 'Chester / Merseyside (UK)',
    '85182c8ffffffff': 'Dublin (Ireland)',
    '85195d8bfffffff': 'Milton Keynes (UK)',
    '851f2113fffffff': 'Halland–Jönköping (Sweden)',
    '853970abfffffff': 'Zaragoza (Spain)',
    '8508b0affffffff': 'Laxå, Örebro / Västra Götaland border (SE)',
}
rows = []   # (section, check, expected, got, status, note)


def check(section, name, expected, got, note='', tol=0.0):
    ok = abs(float(expected) - float(got)) <= tol
    rows.append((section, name, expected, got, 'PASS' if ok else 'FAIL', '' if ok else note))


def totals(counts, base):
    return S.summary(counts, base, 'k').set_index('k')


t0 = time.time()
for f in (HEX_FILE, COUNTRY_FILE):
    require(f)
for f in ('wq_sensitivity', 'rho_sensitivity', 'ca2_sensitivity', 'peak_factor_ops', 'peak_factor_tiers'):
    require(REF / f'{f}.csv')
hexes, countries = load_study_area()
base = int(hexes['NFCh30m_CouSha'].sum())
print(f'Study area: {len(hexes):,} hexagons, {base:,} fast charging points')

# ------------------------------------------------------------------ sweeps (study-area filter)
counts = {'wq': S.sweep_wq(hexes), 'rho': S.sweep_rho(hexes), 'ca2': S.sweep_ca2(hexes),
          'peak_factor': S.sweep_peak_factor(hexes), 'service_time': S.sweep_service_time(hexes)}
tot = {k: totals(v, base) for k, v in counts.items()}
grid = S.joint_grid_cs2(hexes)
PEAKS = sorted(set(S.PEAK_GRID + [S.SWEDEN_PEAK]))
tiers = S.peak_tiers(hexes, base, PEAKS)
ops = S.peak_ops(hexes, PEAKS)
busy = S.busy_hour(hexes, S.SWEDEN_PEAK)
allc = pd.concat(counts.values(), axis=1)
ctab = S.country_table(allc, hexes, hexes['country'])
print(f'  all sweeps done ({time.time() - t0:.0f} s)')

# ------------------------------------------------------------------ results: csv
cent = hexes.geometry.centroid
base_df = pd.DataFrame({
    'h3_id': hexes['h3_id'], 'country': hexes['country'], 'lon': cent.x, 'lat': cent.y,
    'daily_stops': hexes['MDTN_B_CouSha'], 'lambda_per_h': S.lam_flat(hexes),
    'points': hexes['NFCh30m_CouSha'], 'busy_rho': busy['rho_busy'],
    'busy_wait_min': busy['wq_busy_min'], 'busy_tier': busy['tier']})
base_df.to_csv(CSV / 'baseline_hexagons.csv', index=False)
for k, v in counts.items():
    pd.concat([base_df[['h3_id', 'country', 'lon', 'lat']], v], axis=1).to_csv(CSV / f'sensitivity_{k}.csv', index=False)
fail = base_df[base_df['busy_tier'] != 'Service OK'].copy()
fail.to_csv(CSV / 'busy_hour_failures.csv', index=False)
sat = base_df[base_df['busy_tier'] == 'Saturated'].copy()
sat['name'] = sat['h3_id'].map(SATURATED_NAMES)
sat.to_csv(CSV / 'saturated_areas.csv', index=False)
long = pd.concat([t.reset_index().rename(columns={'k': 'scenario'}).assign(choice=k) for k, t in tot.items()])
long[['choice', 'scenario', 'points', 'delta', 'pct']].to_csv(CSV / 'sensitivity_totals.csv', index=False)
grid.to_csv(CSV / 'joint_grid_wq_rho_cs2.csv', index=False)
ops.to_csv(CSV / 'peak_factor_ops.csv', index=False)
tiers.to_csv(CSV / 'peak_factor_tiers.csv', index=False)

# ------------------------------------------------------------------ results: gpkg
gpkg = RES / 'thor_results.gpkg'
if gpkg.exists():
    gpkg.unlink()
gm = hexes.geometry.reset_index(drop=True)


def layer(df, name):
    g = gpd.GeoDataFrame(df.copy(), geometry=gm.loc[df.index].values, crs=4326)
    g.reset_index(drop=True).to_file(gpkg, layer=name, driver='GPKG')


layer(base_df.drop(columns=['lon', 'lat']), 'baseline_hexagons')
for k, v in counts.items():
    layer(pd.concat([base_df[['h3_id', 'country']], v], axis=1), f'sensitivity_{k}')
layer(fail.drop(columns=['lon', 'lat']), 'busy_hour_failures')
layer(sat.drop(columns=['lon', 'lat']), 'saturated_areas')
cc = countries.rename(columns={'name': 'country'}).merge(ctab.rename(columns={'wq_5': 'baseline_points'}), on='country', how='inner')
cc = cc.drop(columns=['NFCh30m_CouSha'])
cc = cc[['country', 'iso3', 'baseline_points'] + [c for c in cc.columns if c not in ('country', 'iso3', 'baseline_points', 'geometry')] + ['geometry']].rename(columns={'lambda': 'lambda_per_h'})
cc = cc.merge(hexes.groupby('country').size().rename('n_hexagons'), left_on='country', right_index=True, how='left')
cc.to_file(gpkg, layer='country_totals', driver='GPKG')
pd.DataFrame(cc.drop(columns='geometry')).to_csv(CSV / 'country_totals.csv', index=False)
print(f'  results written ({time.time() - t0:.0f} s)')

# ------------------------------------------------------------------ section A: paper values, study-area filter
A = 'A paper'
check(A, 'hexagons', 6283, len(hexes))
check(A, 'baseline points', 11877, base)
w, r, c, p, s = (tot[k] for k in ('wq', 'rho', 'ca2', 'peak_factor', 'service_time'))
check(A, 'Wq 3 min, % change', 8.0, w.loc['wq_3', 'pct'])
check(A, 'Wq 30 min, % change', -18.0, w.loc['wq_30', 'pct'])
check(A, 'rho 0.50, % change', 14.3, r.loc['rho_50', 'pct'])
check(A, 'rho 0.50, added points', 1698, r.loc['rho_50', 'delta'])
check(A, 'rho 0.75, added points', 113, r.loc['rho_75', 'delta'])
check(A, 'rho 0.95/0.97/0.99, change', 0, abs(r.loc[['rho_95', 'rho_97', 'rho_99'], 'delta']).sum())
check(A, 'Ca2 1.5, % change', 6.2, c.loc['ca2_1p5', 'pct'])
check(A, 'Ca2 2, % change', 10.9, c.loc['ca2_2p0', 'pct'])
check(A, 'Ca2 3, % change', 18.0, c.loc['ca2_3p0', 'pct'])
check(A, 'Ca2 1.5, added points', 733, c.loc['ca2_1p5', 'delta'])
check(A, 'Ca2 2, added points', 1289, c.loc['ca2_2p0', 'delta'])
check(A, 'Ca2 2, total points', 13166, c.loc['ca2_2p0', 'points'])
check(A, 'Ca2 3, added points', 2142, c.loc['ca2_3p0', 'delta'])
check(A, 'peak 1.666, added points', 806, p.loc['p_1p666', 'delta'])
check(A, 'peak 1.666, % change', 6.8, p.loc['p_1p666', 'pct'])
check(A, 'peak 1.44 (flat-day equivalent), added points', 0, p.loc['p_1p44', 'delta'])
check(A, 'peak 1.0, added points', -1609, p.loc['p_1p0', 'delta'])
check(A, 'peak 1.6, added points', 574, p.loc['p_1p6', 'delta'])
check(A, 'peak 2.0, added points', 1924, p.loc['p_2p0', 'delta'])
sw = tiers[tiers['peak'] == S.SWEDEN_PEAK].iloc[0]
for nm, e in zip(S.TIER_NAMES, (7, 11, 761, 5504)):
    check(A, f'busy-hour tier {nm} (n)', e, sw[f'{nm}_n'])
nfail = sum(int(sw[f'{n}_n']) for n in S.TIER_NAMES[:3])
check(A, 'failing hexagons', 779, nfail)
o = ops[ops['peak'] == S.SWEDEN_PEAK].iloc[0]
check(A, 'failing share of hexagons, %', 12.4, round(o['failed_pct_count'], 1))
check(A, 'failing share of busy-hour truck-hours, %', 47.2, round(o['failed_pct_demand'], 1))
for k, e in (('svc_15', 8465), ('svc_20', 9589), ('svc_30', 11877), ('svc_45', 15230), ('svc_60', 18396)):
    check(A, f'service time {k[4:]} min, points', e, s.loc[k, 'points'])
check(A, 'service time 15 min, % change', -28.7, s.loc['svc_15', 'pct'])
check(A, 'service time 60 min, % change', 54.9, s.loc['svc_60', 'pct'])
g1 = grid[(grid['Wq_min'] == 5) & (grid['rho_max'] == 0.95)].set_index('Cs2')['points']
check(A, 'M/D/c (Cs2=0) change vs baseline, points', -48, g1.loc[0.0] - base)
check(A, 'exponential service (Cs2=1) change, points', 1259, g1.loc[1.0] - base)
check(A, 'exponential service (Cs2=1) total points', 13136, g1.loc[1.0])

# ------------------------------------------------------------------ section B: replicate notebook CSVs on the notebook filter
B = 'B old filter'
hx, ct = gpd.read_file(HEX_FILE), gpd.read_file(COUNTRY_FILE)
valid = ct[~ct['name'].isin(EXCLUDE_COUNTRIES)]
leg = hx[hx.geometry.centroid.within(valid.union_all())]
leg = leg[leg['NFCh30m_CouSha'] > 0].reset_index(drop=True)
lbase = int(leg['NFCh30m_CouSha'].sum())
check(B, 'notebook-filter baseline points', 11878, lbase)
lc = {'wq': S.sweep_wq(leg), 'rho': S.sweep_rho(leg), 'ca2': S.sweep_ca2(leg)}
lt = {k: totals(v, lbase) for k, v in lc.items()}
for _, rr in pd.read_csv(REF / 'wq_sensitivity.csv').iterrows():
    check(B, f'wq_sensitivity Wq={int(rr.Wq_min)} points', rr.NFCh30m, lt['wq'].loc[f'wq_{int(rr.Wq_min)}', 'points'])
for _, rr in pd.read_csv(REF / 'rho_sensitivity.csv').iterrows():
    check(B, f'rho_sensitivity rho={rr.rho_max} points', rr.NFCh30m,
          lt['rho'].loc[f'rho_{int(round(rr.rho_max * 100))}', 'points'])
for _, rr in pd.read_csv(REF / 'ca2_sensitivity.csv').iterrows():
    check(B, f'ca2_sensitivity Ca2={rr.Ca2} points', rr.total_bays,
          lt['ca2'].loc[f'ca2_{str(rr.Ca2).replace(".", "p")}', 'points'])
lpk = S.sweep_peak_factor(leg)
lsv = S.sweep_service_time(leg)
for k, e in (('svc_15', 8466), ('svc_20', 9590), ('svc_45', 15232), ('svc_60', 18399)):
    check(B, f'service time {k[4:]} min points (paper)', e, int(lsv[k].sum()))
check(B, 'Ca2 3 added points (paper)', 2143, lt['ca2'].loc['ca2_3p0', 'delta'])
check(B, 'peak 2.0 added points (paper)', 1925, int(lpk['p_2p0'].sum()) - lbase)
lops = S.peak_ops(leg)
for _, rr in pd.read_csv(REF / 'peak_factor_ops.csv').iterrows():
    got = lops[lops['peak'] == rr.peak].iloc[0]
    for col in ('failed_pct_count', 'failed_pct_demand', 'wq_dw_min', 'rho_dw', 'n_saturated'):
        check(B, f'peak_factor_ops p={rr.peak} {col}', rr[col], got[col], tol=1e-9)
ltr = S.peak_tiers(leg, lbase)
for _, rr in pd.read_csv(REF / 'peak_factor_tiers.csv').iterrows():
    got = ltr[ltr['peak'] == rr.peak].iloc[0]
    for col in [f'{n}_n' for n in S.TIER_NAMES] + ['bays_needed', 'extra_bays']:
        check(B, f'peak_factor_tiers p={rr.peak} {col}', rr[col], got[col])
lcent = leg.copy()
lcent['geometry'] = lcent.geometry.centroid
lj = gpd.sjoin(lcent, valid[['name', 'geometry']], how='left', predicate='within')
lj = lj[~lj.index.duplicated()]
lct = S.country_table(pd.concat([lc['wq'], lc['rho']], axis=1), leg, lj['name'].values).set_index('country')
# data/reference/country_sensitivity.csv was dropped (older model state). Country checks use paper values.
check(B, 'number of countries with >= 20 baseline points', 34, len(lct))
for ctry, col, e in (('Slovakia', 'S_wq', 0.356), ('Slovenia', 'S_wq', 0.356), ('Ireland', 'S_rho', 0.308),
                     ('Luxembourg', 'S_rho', 0.308)):
    check(B, f'country {ctry} {col} (3 d.p.)', e, round(float(lct.loc[ctry, col]), 3))
check(B, 'country median S_wq (3 d.p.)', 0.241, round(float(lct['S_wq'].median()), 3))
check(B, 'country median S_rho (3 d.p.)', 0.029, round(float(lct['S_rho'].median()), 3))
check(A, 'country median S_rho on study filter (3 d.p.)', 0.029, round(float(ctab['S_rho'].median()), 3))

# ------------------------------------------------------------------ table
df = pd.DataFrame(rows, columns=['section', 'check', 'expected', 'got', 'status', 'cause if FAIL'])
df.to_csv(RES / 'acceptance_checks.csv', index=False)
pd.set_option('display.width', 250, 'display.max_colwidth', 90, 'display.max_rows', 1000)
sh = df.drop(columns='cause if FAIL').copy()
for col in ('expected', 'got'):
    sh[col] = sh[col].map(lambda v: f'{v:,.6g}')
print('\n' + sh.to_string(index=False))
print('\nSummary by section:')
print(df.groupby(['section', 'status']).size().unstack(fill_value=0).to_string())
print('A: paper values on the single study-area filter (11,877 points).')
print('B: reproduction check of the earlier notebook filter (EPSG:4326 centroids, 11,878 points); not the paper filter.')
failed = df[df['status'] == 'FAIL']
if len(failed):
    print('\nFAIL causes:')
    print(failed[['section', 'check', 'cause if FAIL']].to_string(index=False))
print(f'\nTotal runtime {time.time() - t0:.0f} s')
