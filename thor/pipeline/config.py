# -*- coding: utf-8 -*-
"""
Pipeline configuration — edit this file before running any script.

All input paths, output paths, and model parameters are defined here.
The five pipeline scripts import their settings from this module, so you
only need to change values in one place.

Running order:
  01_generate_route_points.py        # ~hours
  02_apply_rest_break_rules.py       # ~hours
  03_aggregate_to_grid.py            # minutes  (independent of 04 and 05)
  04_summarise_by_origin.py          # seconds  (independent of 03 and 05)
  05_summarise_by_country.py         # seconds  (independent of 03 and 04)
"""

import os
import pandas as pd

# ---------------------------------------------------------------------------
# Input data — edit these paths to match your system
# ---------------------------------------------------------------------------

# Annual truck and tonnage flows between NUTS-3 zone pairs (OD matrix)
FLOW_CSV = r'D:\STORM\Freight_Model_2030\01_Trucktrafficflow.csv'

# NUTS-3 zone table: ETISPlus zone IDs and geometric centroid coordinates
NUTS3_CSV = r'D:\STORM\Freight_Model_2030\02_NUTS-3-Regions.csv'

# Road network node coordinates (node ID, X, Y)
NODES_CSV = r'D:\STORM\Freight_Model_2030\03_network-nodes.csv'

# Road network edges: speed class, traffic counts, routed edge-path strings
EDGES_CSV = r'D:\STORM\Freight_Model_2030\Updated_04_network-edges.csv'

# NUTS-3 centroid shapefile — provides geometry and CRS for output files
CENTROIDS_SHP = r'D:\STORM\Freight_Model_2030\Centroids.shp'

# M/G/c queuing-model lookup tables for charger sizing
QUEUE_30MIN_CSV = r'D:\STORM\Freight_Model_2030\queue_30min.csv'
QUEUE_60MIN_CSV = r'D:\STORM\Freight_Model_2030\queue_60min.csv'

# EU + Turkey country boundary polygons (used for spatial aggregation)
EU_COUNTRIES_SHP = r'D:\STORM\EU cont\EU_contriesWithTurk.shp'

# Reference grid for spatial aggregation in script 03 (legacy square grid — no longer used).
REFERENCE_GRID_SHP = r'D:\STORM\Outputs\figures\RestBreakFileAgg.shp'

# H3 resolution-5 hexagon grid for spatial aggregation in script 03.
# Merged from vesuvio_hexagons.shp + vesuvio_hexagons_missing.shp (91,650 cells, EPSG:4326).
HEXAGONS_SHP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inputData', 'hexagons_eu.gpkg')

# ---------------------------------------------------------------------------
# Output paths — generated relative to this config file's location
# ---------------------------------------------------------------------------

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Root folder for all pipeline outputs
BASE_OUTPUT_DIR = os.path.join(_PROJECT_DIR, 'outputs')

# Sub-folder for per-route point shapefiles (one .shp per OD pair, from script 01)
ROUTE_POINTS_DIR = os.path.join(BASE_OUTPUT_DIR, 'route_points')

# Aggregated stop/rest event file written by script 02 and read by scripts 03–05.
# Pointing to the existing CheckingOldFiles run — replace with the Thor outputs path
# (os.path.join(BASE_OUTPUT_DIR, 'stop_rest_events.shp')) once scripts 01 and 02 are run.
STOP_REST_FILE = r'C:\Users\shoman\Desktop\Projects\STORM\CheckingOldFiles\inputData\RestandBreaksPoints.shp'

# ---------------------------------------------------------------------------
# Route generation — script 01
# ---------------------------------------------------------------------------

# Geodesic distance between consecutive points placed along each route (km)
POINT_SPACING_KM = 10

# Minimum straight-line OD distance to be classified as long-haul freight (km)
# Routes shorter than this are skipped.
MIN_HAUL_KM = 200

# Minimum annual tonnage flow required to include an OD pair (tonnes/year)
MIN_FLOW_TONS_2030 = 50

# Number of parallel worker processes for route generation.
# None uses all available CPU cores.
N_WORKERS = None

# ---------------------------------------------------------------------------
# Rest/break rule engine — script 02 (EU Regulation 561/2006)
# ---------------------------------------------------------------------------

# Minimum daily truck flow required to process a route (trucks/day, 2019 data)
MIN_FLOW_TRUCKS_2019 = 50

# Minimum total route distance to apply rest/break rules (km).
# Routes below this threshold produce no stop events.
MIN_DISTANCE_KM = 270

# Road segments longer than this threshold are treated as geometry gaps
# caused by disconnected network edges and have their distance zeroed (km).
MAX_SEGMENT_KM = 50

# Speed code that identifies ferry/passive segments in the network edge data.
# Points on these segments do not accumulate driving time toward a break.
FERRY_SPEED_CODE = 22

# Accumulated driving time that triggers a mandatory break (minutes)
BREAK_THRESHOLD_MIN = 270          # 4.5 hours

# Duration of a mandatory short break (minutes)
BREAK_DURATION_MIN = 45

# Duration of a daily rest period (minutes)
REST_DURATION_MIN = 540            # 9 hours

# Maximum estimated trip duration for the single-driver regime (minutes).
# Trips at or above this threshold use the two-driver regime.
ONE_DRIVER_MAX_MIN = 900           # 15 hours

# Number of 45-min breaks before the daily rest in the single-driver regime
SINGLE_DRIVER_BREAKS = 1

# Number of 45-min breaks before the daily rest in the two-driver regime
TWO_DRIVER_BREAKS = 3

# Energy consumption rates by road speed
ENERGY_RATE_LOW_KWH_KM  = 1.2     # kWh/km at speeds below ENERGY_SPEED_THRESHOLD
ENERGY_RATE_HIGH_KWH_KM = 1.8     # kWh/km at speeds at or above ENERGY_SPEED_THRESHOLD
ENERGY_SPEED_THRESHOLD_KMH = 80   # km/h

# Network edge IDs where EV charging is not available (e.g. ferry crossings,
# toll-free segments without charging infrastructure).
# Trucks on these edges do not accumulate charging demand.
NO_CHARGE_EDGE_IDS = {
    '2616052', '2616030', '2616212', '2615991', '2615977',
    '2615998', '2615983', '1031291', '1033183', '2501131',
    '1033092', '2616071', '1069947',
}

# ---------------------------------------------------------------------------
# Grid aggregation — script 03
# ---------------------------------------------------------------------------

# Grid cell size for spatial aggregation of charging demand (metres, EPSG:3035)
GRID_SIZE_M = 25_000

# Equal-area CRS used for grid construction — ensures all cells are the same size
GRID_CRS = 'EPSG:3035'

# ---------------------------------------------------------------------------
# EV market scenario — scripts 03, 04, 05
# ---------------------------------------------------------------------------

# BET stock share data from the vesuvio project (country-specific EV shares)
PARAMS_FILE = r'C:\Users\shoman\Desktop\Projects\vesuvio-main\Parameters_Input.xlsx'

# Scenario and year to use from the BET stock share table
EV_SCENARIO    = 'medium'
EV_TARGET_YEAR = 2030

# Original flat assumption from the trip-based model publication — used for the _15Co comparison columns
EV_SHARE_FLAT = 0.15              # 15%

# Fallback share for any country not present in the lookup table.
# Set dynamically to the mean of all 42 country-specific shares (computed below).
EV_SHARE_MAIN = None              # placeholder — assigned after EV_SHARE_BY_COUNTRY is built


def _build_ev_share_dict():
    """
    Load per-country EV shares from Parameters_Input.xlsx.

    The bet_stock_share sheet has four combinations: rigid/tractor x longhaul/regional.
    Rigid equals tractor in every country, but regional is ~11 pp higher than longhaul
    in 41 of 42 countries.  We take a simple average across all four combinations so
    that no single sub-category is privileged.
    """
    raw = pd.read_excel(PARAMS_FILE, sheet_name='bet_stock_share', header=0)
    raw.columns = [
        'parameter', 'country', 'truck_type', 'scenario', 'application', 'unit',
        2020, 2025, 2030, 2035, 2040, 2045, 2050, 'source', 'notes',
    ]
    avg = (
        raw[raw['scenario'] == EV_SCENARIO]
        .groupby('country')[EV_TARGET_YEAR]
        .mean()
    )
    d = avg.to_dict()
    if 'UK' in d:
        d['GB'] = d['UK']   # EU countries shapefile uses GB; NUTS3 CSV uses UK — keep both
    return d


# Dict: ISO 3166-1 alpha-2 country code → average BET stock share (fraction).
# Average is taken across all four truck-type/application combinations (medium scenario).
# Countries not present fall back to EV_SHARE_MAIN.
EV_SHARE_BY_COUNTRY = _build_ev_share_dict()

# Mean of all 42 unique country shares — used as fallback for unlisted countries.
# GB is excluded from the mean because it is a duplicate of UK.
EV_SHARE_MAIN = sum(v for k, v in EV_SHARE_BY_COUNTRY.items() if k != 'GB') / sum(
    1 for k in EV_SHARE_BY_COUNTRY if k != 'GB'
)

# Working days per year — converts annual OD flows to average daily demand
ANNUAL_WORKING_DAYS = 300

# Average truck payload used to convert annual tonnage to truck counts
TRUCK_CAPACITY_T = 13.6           # tonnes per truck
