"""Load model inputs and apply the study-area filter."""
from pathlib import Path
import sys
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
HEX_FILE = ROOT / 'data' / 'input' / 'charging_demand_hexagons.gpkg'
COUNTRY_FILE = ROOT / 'data' / 'input' / 'countries.gpkg'
EXCLUDE_COUNTRIES = {'Russian Federation', 'Turkey'}


def require(path):
    if not Path(path).exists():
        sys.exit(f'Missing input file: {path}\nSee README section "Data".')
    return Path(path)


def load_study_area():
    """Return (hexes, countries).

    Hexagon centroids (EPSG:3035) are joined `within` the country polygons. Rows are kept when the
    country name is not null and not Russia/Turkey, and NFCh30m_CouSha > 0.
    The result has 6,283 hexagons and 11,877 fast charging points.
    """
    hexes = gpd.read_file(require(HEX_FILE))
    countries = gpd.read_file(require(COUNTRY_FILE))
    hexes = hexes[hexes['NFCh30m_CouSha'] > 0].copy()
    cent = hexes.to_crs(3035).copy()
    cent['geometry'] = cent.geometry.centroid
    joined = gpd.sjoin(cent, countries.to_crs(3035)[['name', 'geometry']], predicate='within', how='left')
    joined = joined[~joined.index.duplicated()]
    ok = (~joined['name'].isin(EXCLUDE_COUNTRIES)) & joined['name'].notna()
    hexes = hexes.loc[joined.index[ok]].copy()
    hexes['country'] = joined.loc[hexes.index, 'name']
    hexes = hexes.reset_index(drop=True)
    return hexes, countries
