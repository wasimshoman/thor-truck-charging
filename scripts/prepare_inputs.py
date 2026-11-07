"""One-time builder of data/input/ from the author's working files.

Usage: python scripts/prepare_inputs.py HEXAGONS_GPKG COUNTRIES_SHP PARAMETERS_XLSX
Not needed to reproduce the results; data/input/ is already in the repository.
"""
import sys
from pathlib import Path
import pandas as pd
import geopandas as gpd
import h3

ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) != 4:
    sys.exit(__doc__)
hex_src, ctry_src, xlsx = map(Path, sys.argv[1:])
for p in (hex_src, ctry_src, xlsx):
    if not p.exists():
        sys.exit(f'Missing: {p}')
out = ROOT / 'data' / 'input'
h = gpd.read_file(hex_src).to_crs(4326)
c = h.geometry.centroid
h['h3_id'] = [h3.latlng_to_cell(y, x, 5) for x, y in zip(c.x, c.y)]
assert h['h3_id'].is_unique
h[['h3_id', 'MDTN_B_CouSha', 'NFCh30m_CouSha', 'geometry']].to_file(out / 'charging_demand_hexagons.gpkg', driver='GPKG')
ct = gpd.read_file(ctry_src).to_crs(4326)[['name', 'iso3', 'geometry']]
ct.to_file(out / 'countries.gpkg', driver='GPKG')
raw = pd.read_excel(xlsx, sheet_name='bet_stock_share', header=0)
raw.columns = ['parameter', 'country', 'truck_type', 'scenario', 'application', 'unit',
               2020, 2025, 2030, 2035, 2040, 2045, 2050, 'source', 'notes']
s = raw[raw['scenario'] == 'medium'].groupby('country')[2030].mean()
s.rename('bet_share_2030').rename_axis('country_iso2').reset_index().to_csv(out / 'bet_share_by_country.csv', index=False)
print('written', list(out.iterdir()))
