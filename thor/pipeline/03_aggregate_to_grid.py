# -*- coding: utf-8 -*-
"""
Script 03 — Aggregate stop/rest events to an H3 hexagon grid and size chargers.

Reads the stop/rest events from script 02 and produces spatial summaries
at two levels:

  Hexagon level (charging_demand_hexagons.gpkg):
    Each populated H3 resolution-5 hexagon (~609 km²) reports the estimated
    number of fast chargers (30-min and 60-min CCS) and slow chargers
    (overnight MCS) required to serve the EV truck demand at that location.
    Charger counts are derived from a pre-computed M/G/c queuing model table.

  Country level (country_summary.csv / .gpkg):
    Hexagon cells are spatially joined to country boundaries and aggregated
    to give a per-country breakdown of charging infrastructure demand and
    daily energy consumption.

The hexagon grid is loaded from HEXAGONS_SHP (set in config.py) — a pre-
generated H3 resolution-5 grid covering EU + Turkey from the vesuvio project.
"""

import os
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    STOP_REST_FILE, BASE_OUTPUT_DIR, NUTS3_CSV,
    QUEUE_30MIN_CSV, QUEUE_60MIN_CSV, EU_COUNTRIES_SHP,
    HEXAGONS_SHP,
    EV_SHARE_MAIN, EV_SHARE_BY_COUNTRY, EV_SHARE_FLAT, EV_TARGET_YEAR,
    ANNUAL_WORKING_DAYS, TRUCK_CAPACITY_T,
)


# ---------------------------------------------------------------------------
# Queuing model lookup
# ---------------------------------------------------------------------------

def _lookup_chargers(lambda_val, queue_df):
    """
    Return the minimum number of charger bays for the given hourly arrival
    rate, using the pre-computed M/G/c queuing model table.

    For arrival rates beyond the table range the result is extrapolated in
    chunks of 152 arrivals/hour (the table's maximum modelled rate).
    """
    if lambda_val <= 0:
        return 0
    matches = queue_df[queue_df['lambda'] > lambda_val]
    if not matches.empty:
        return int(matches.iloc[0]['servers'])
    whole     = int(lambda_val // 152)
    remaining = lambda_val % 152
    tail      = queue_df[queue_df['lambda'] > remaining]
    extra     = int(tail.iloc[0]['servers']) if not tail.empty else 0
    return int(80 * whole + extra)


# ---------------------------------------------------------------------------
# Step 1 — attach country-specific EV shares and enrich stop/rest events
# ---------------------------------------------------------------------------

def _attach_ev_shares(gdf):
    """
    Add an 'ev_share' column to each stop/rest event based on the origin
    zone's country.  Uses the average BET stock share across all four
    truck-type/application combinations (medium scenario, 2030) loaded from
    Parameters_Input.xlsx; falls back to EV_SHARE_MAIN for any zone whose
    country is not in the lookup table.
    """
    nuts3 = pd.read_csv(NUTS3_CSV, usecols=['ETISPlus_Zone_ID', 'Country'])
    zone_country = nuts3.set_index('ETISPlus_Zone_ID')['Country']
    gdf = gdf.copy()
    country_codes = gdf['ID_origin_'].astype(int).map(zone_country)
    gdf['ev_share'] = country_codes.map(EV_SHARE_BY_COUNTRY).fillna(EV_SHARE_MAIN)
    return gdf


def _enrich_events(gdf):
    """
    Derive charging demand columns from the flow and energy data.

    MainDTN  — daily trucks needing a charge at this stop (country-specific EV share)
    ChEMain  — energy charged per stop event (MWh)
    ChE30M   — weighted energy (MWh) = ChEMain × MainDTN
    ChERM    — energy at rest stops with slow chargers (MWh)
    ChEBM    — energy at break stops with fast chargers (MWh)
    MDTN_R   — daily trucks using slow chargers (rest stops)
    MDTN_B   — daily trucks using fast chargers (break stops)
    ChER100  — energy at rest stops at 100% electrification (MWh)
    ChEB100  — energy at break stops at 100% electrification (MWh)
    DTN100_R — daily trucks at rest stops, 100% electrification
    DTN100_B — daily trucks at break stops, 100% electrification
    """
    gdf = gdf.copy()
    gdf['ChEMain'] = pd.to_numeric(gdf['ChaEnekWh']) / 1000
    gdf['Rest']    = pd.to_numeric(gdf['Rest'])
    gdf['Break']   = pd.to_numeric(gdf['Break'])

    # --- _CouSha: country-specific EV share (NEW scenario) ---
    gdf['MainDTN']   = gdf['YFlow(30)'] / ANNUAL_WORKING_DAYS * gdf['ev_share'] / TRUCK_CAPACITY_T  # NEW
    gdf['ChE30M']    = gdf['ChEMain'] * gdf['MainDTN']    # NEW
    gdf['ChERM']     = gdf['Rest']  * gdf['ChE30M']       # NEW
    gdf['MDTN_R']    = gdf['Rest']  * gdf['MainDTN']      # NEW
    gdf['ChEBM']     = gdf['Break'] * gdf['ChE30M']       # NEW
    gdf['MDTN_B']    = gdf['Break'] * gdf['MainDTN']      # NEW

    # --- _15Co: flat 15% share (OLD scenario — for comparison) ---
    gdf['MainDTN_f'] = gdf['YFlow(30)'] / ANNUAL_WORKING_DAYS * EV_SHARE_FLAT / TRUCK_CAPACITY_T  # OLD
    gdf['ChE30M_f']  = gdf['ChEMain'] * gdf['MainDTN_f']  # OLD
    gdf['ChERM_f']   = gdf['Rest']  * gdf['ChE30M_f']     # OLD
    gdf['MDTN_R_f']  = gdf['Rest']  * gdf['MainDTN_f']    # OLD
    gdf['ChEBM_f']   = gdf['Break'] * gdf['ChE30M_f']     # OLD
    gdf['MDTN_B_f']  = gdf['Break'] * gdf['MainDTN_f']    # OLD

    # --- Unchanged (100% electrification scenario) ---
    gdf['ChER100']  = gdf['Rest']  * gdf['ChEMain'] * gdf['DTN30_100']
    gdf['ChEB100']  = gdf['Break'] * gdf['ChEMain'] * gdf['DTN30_100']
    gdf['DTN100_R'] = gdf['Rest']  * gdf['YFlow(30)'] / ANNUAL_WORKING_DAYS / TRUCK_CAPACITY_T
    gdf['DTN100_B'] = gdf['Break'] * gdf['YFlow(30)'] / ANNUAL_WORKING_DAYS / TRUCK_CAPACITY_T
    return gdf


# ---------------------------------------------------------------------------
# Step 2 — load hexagon grid
# ---------------------------------------------------------------------------

def _load_hexagons():
    """Load the pre-generated H3 resolution-5 hexagon grid from HEXAGONS_SHP."""
    hex_gdf = gpd.read_file(HEXAGONS_SHP)[['geometry']].copy()
    hex_gdf['cell_id'] = range(len(hex_gdf))
    return hex_gdf


# ---------------------------------------------------------------------------
# Step 3 — spatial join and aggregate
# ---------------------------------------------------------------------------

def _aggregate_to_grid(rb_gdf, grid_gdf, queue_30, queue_60):
    """
    Spatially join stop/rest events to hexagon cells and compute per-cell
    aggregates and charger counts.
    """
    rb_4326 = rb_gdf.to_crs('EPSG:4326')
    joined  = gpd.sjoin(
        rb_4326,
        grid_gdf[['cell_id', 'geometry']],
        how='left',
        predicate='within',
    )

    agg = (
        joined.dropna(subset=['cell_id'])
        .groupby('cell_id')
        .agg(
            # Unchanged (100% electrification)
            SUM_DTN30_ = ('DTN30_100', 'sum'),
            SUM_DTN301 = ('DTN30_30',  'sum'),
            SUM_ChaEne = ('ChaEnekWh', 'sum'),
            SUM_ChER10 = ('ChER100',   'sum'),
            SUM_ChEB10 = ('ChEB100',   'sum'),
            SUM_DTNB10 = ('DTN100_B',  'sum'),
            SUM_DTNR10 = ('DTN100_R',  'sum'),
            # _CouSha: country-specific share (NEW)
            SUM_MainDT = ('MainDTN',   'sum'),
            SUM_ChE30M = ('ChE30M',    'sum'),
            SUM_ChERM  = ('ChERM',     'sum'),
            SUM_MDTN_R = ('MDTN_R',    'sum'),
            SUM_ChEBM  = ('ChEBM',     'sum'),
            SUM_MDTN_B = ('MDTN_B',    'sum'),
            # _15Co: flat 15% share (OLD)
            SUM_MDT_f  = ('MainDTN_f', 'sum'),
            SUM_CE30_f = ('ChE30M_f',  'sum'),
            SUM_CERM_f = ('ChERM_f',   'sum'),
            SUM_MR_f   = ('MDTN_R_f',  'sum'),
            SUM_CEBM_f = ('ChEBM_f',   'sum'),
            SUM_MB_f   = ('MDTN_B_f',  'sum'),
        )
        .round(2)
        .reset_index()
    )

    grid_out = grid_gdf.merge(agg, on='cell_id', how='inner').drop(columns=['cell_id'])

    # Unchanged (100% electrification scenario)
    grid_out['DTN100'] = grid_out['SUM_DTN30_']
    grid_out['DTN30']  = grid_out['SUM_DTN301']
    grid_out['ChE100'] = grid_out['SUM_ChaEne'] / 1000
    grid_out['NFCh100'] = grid_out['SUM_DTNB10'].apply(
        lambda v: _lookup_chargers(v * 0.06, queue_30))
    grid_out['NSCh100'] = np.ceil(grid_out['SUM_DTNR10'] / 2).astype(int)

    # _CouSha: country-specific EV share (NEW scenario)
    grid_out['MainDTN_CouSha']  = grid_out['SUM_MainDT']                  # NEW
    grid_out['ChE30_CouSha']    = grid_out['SUM_ChE30M']                   # NEW
    grid_out['ChERM_CouSha']    = grid_out['SUM_ChERM']                    # NEW
    grid_out['MDTN_R_CouSha']   = grid_out['SUM_MDTN_R']                  # NEW
    grid_out['ChEBM_CouSha']    = grid_out['SUM_ChEBM']                    # NEW
    grid_out['MDTN_B_CouSha']   = grid_out['SUM_MDTN_B']                  # NEW
    grid_out['NSCh2pD_CouSha']  = np.ceil(grid_out['MDTN_R_CouSha'] / 2).astype(int)  # NEW
    grid_out['NFCh30m_CouSha']  = grid_out['MDTN_B_CouSha'].apply(
        lambda v: _lookup_chargers(v * 0.06, queue_30))                    # NEW
    grid_out['TotCha_CouSha']   = grid_out['NSCh2pD_CouSha'] + grid_out['NFCh30m_CouSha']  # NEW
    grid_out['NFCh1H_CouSha']   = grid_out['MDTN_B_CouSha'].apply(
        lambda v: _lookup_chargers(v * 0.06, queue_60))                    # NEW

    # _15Co: flat 15% share (OLD scenario — for comparison)
    grid_out['MainDTN_15Co']    = grid_out['SUM_MDT_f']                    # OLD
    grid_out['ChE30_15Co']      = grid_out['SUM_CE30_f']                   # OLD
    grid_out['ChERM_15Co']      = grid_out['SUM_CERM_f']                   # OLD
    grid_out['MDTN_R_15Co']     = grid_out['SUM_MR_f']                     # OLD
    grid_out['ChEBM_15Co']      = grid_out['SUM_CEBM_f']                   # OLD
    grid_out['MDTN_B_15Co']     = grid_out['SUM_MB_f']                     # OLD
    grid_out['NSCh2pD_15Co']    = np.ceil(grid_out['MDTN_R_15Co'] / 2).astype(int)    # OLD
    grid_out['NFCh30m_15Co']    = grid_out['MDTN_B_15Co'].apply(
        lambda v: _lookup_chargers(v * 0.06, queue_30))                    # OLD
    grid_out['TotCha_15Co']     = grid_out['NSCh2pD_15Co'] + grid_out['NFCh30m_15Co'] # OLD
    grid_out['NFCh1H_15Co']     = grid_out['MDTN_B_15Co'].apply(
        lambda v: _lookup_chargers(v * 0.06, queue_60))                    # OLD

    return gpd.GeoDataFrame(grid_out, geometry='geometry', crs='EPSG:4326')


# ---------------------------------------------------------------------------
# Step 4 — country-level summary
# ---------------------------------------------------------------------------

def _summarise_by_country(grid_gdf, countries_gdf):
    grid_4326 = grid_gdf.to_crs('EPSG:4326')
    countries = countries_gdf.to_crs('EPSG:4326')

    joined = gpd.sjoin(
        grid_4326,
        countries[['name', 'geometry']],
        how='inner',
        predicate='intersects',
    )

    grouped = (
        joined.groupby('name')
        .agg(
            NumberOfStations                  = ('geometry',       'count'),
            # Unchanged (100% electrification)
            ChargedEnergy_MWh_100pct          = ('ChE100',         'sum'),
            DailyTrucks_100pct                = ('DTN100',         'sum'),
            FastChargingPoints_30min_100pct   = ('NFCh100',        'sum'),
            SlowChargingPoints_100pct         = ('NSCh100',        'sum'),
            # _CouSha: country-specific EV share (NEW)
            DailyTrucksAtStops_CouSha         = ('MainDTN_CouSha', 'sum'),
            ChargedEnergy_MWh_CouSha          = ('ChE30_CouSha',   'sum'),
            SlowChargerEnergy_MWh_CouSha      = ('ChERM_CouSha',   'sum'),
            DailyTrucksSlowChargers_CouSha    = ('MDTN_R_CouSha',  'sum'),
            FastChargerEnergy_MWh_CouSha      = ('ChEBM_CouSha',   'sum'),
            DailyTrucksFastChargers_CouSha    = ('MDTN_B_CouSha',  'sum'),
            SlowChargingPoints_CouSha         = ('NSCh2pD_CouSha', 'sum'),
            FastChargingPoints_30min_CouSha   = ('NFCh30m_CouSha', 'sum'),
            TotalChargingPoints_CouSha        = ('TotCha_CouSha',  'sum'),
            FastChargingPoints_60min_CouSha   = ('NFCh1H_CouSha',  'sum'),
            # _15Co: flat 15% share (OLD)
            DailyTrucksAtStops_15Co           = ('MainDTN_15Co',   'sum'),
            ChargedEnergy_MWh_15Co            = ('ChE30_15Co',     'sum'),
            SlowChargerEnergy_MWh_15Co        = ('ChERM_15Co',     'sum'),
            DailyTrucksSlowChargers_15Co      = ('MDTN_R_15Co',    'sum'),
            FastChargerEnergy_MWh_15Co        = ('ChEBM_15Co',     'sum'),
            DailyTrucksFastChargers_15Co      = ('MDTN_B_15Co',    'sum'),
            SlowChargingPoints_15Co           = ('NSCh2pD_15Co',   'sum'),
            FastChargingPoints_30min_15Co     = ('NFCh30m_15Co',   'sum'),
            TotalChargingPoints_15Co          = ('TotCha_15Co',    'sum'),
            FastChargingPoints_60min_15Co     = ('NFCh1H_15Co',    'sum'),
        )
        .reset_index()
        .rename(columns={'name': 'Country'})
    )
    return grouped, joined


def _print_summary(grid_gdf, grouped):
    print('\n{:<35} {:>12} {:>12}'.format('', '_CouSha (NEW)', '_15Co (OLD)'))
    print('-' * 60)
    print('{:<35} {:>12,.0f} {:>12,.0f}'.format(
        'Fast chargers (30 min)',
        grid_gdf['NFCh30m_CouSha'].sum(), grid_gdf['NFCh30m_15Co'].sum()))
    print('{:<35} {:>12,.0f} {:>12,.0f}'.format(
        'Slow chargers (2/day)',
        grid_gdf['NSCh2pD_CouSha'].sum(), grid_gdf['NSCh2pD_15Co'].sum()))
    print('{:<35} {:>12,.0f} {:>12,.0f}'.format(
        'Total chargers',
        grid_gdf['TotCha_CouSha'].sum(), grid_gdf['TotCha_15Co'].sum()))
    print('{:<35} {:>12,.0f} {:>12,.0f}'.format(
        'Fast chargers (60 min)',
        grid_gdf['NFCh1H_CouSha'].sum(), grid_gdf['NFCh1H_15Co'].sum()))
    print('{:<35} {:>12,.1f} {:>12,.1f}'.format(
        'Total daily energy (GWh)',
        grouped['ChargedEnergy_MWh_CouSha'].sum() / 1000,
        grouped['ChargedEnergy_MWh_15Co'].sum() / 1000))
    print('\n=== 100% electrification (unchanged) ===')
    print('  Fast chargers (30 min) : {:>8,.0f}'.format(grid_gdf['NFCh100'].sum()))
    print('  Slow chargers          : {:>8,.0f}'.format(grid_gdf['NSCh100'].sum()))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    t0 = time.time()
    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

    print('Loading inputs...')
    rb_gdf    = gpd.read_file(STOP_REST_FILE)
    queue_30  = pd.read_csv(QUEUE_30MIN_CSV)
    queue_60  = pd.read_csv(QUEUE_60MIN_CSV)
    countries = gpd.read_file(EU_COUNTRIES_SHP)
    print('  {:,} stop/rest events loaded'.format(len(rb_gdf)))

    print('\nStep 1 - attaching country-specific EV shares...')
    rb_gdf = _attach_ev_shares(rb_gdf)
    print('  ev_share range: {:.3f} – {:.3f}'.format(
        rb_gdf['ev_share'].min(), rb_gdf['ev_share'].max()))

    print('\nStep 1b - enriching events with demand columns...')
    rb_gdf = _enrich_events(rb_gdf)
    enriched_path = os.path.join(BASE_OUTPUT_DIR, 'stop_rest_events_enriched.shp')
    rb_gdf.to_file(enriched_path)
    print('  Saved: {}'.format(os.path.basename(enriched_path)))

    print('\nStep 2 - loading hexagon grid ({})...'.format(
        os.path.basename(HEXAGONS_SHP)))
    grid_gdf = _load_hexagons()
    print('  {:,} hexagon cells loaded'.format(len(grid_gdf)))

    print('\nStep 3 - spatial join and aggregation...')
    agg_gdf  = _aggregate_to_grid(rb_gdf, grid_gdf, queue_30, queue_60)
    grid_path = os.path.join(BASE_OUTPUT_DIR, 'charging_demand_hexagons.gpkg')
    agg_gdf.to_file(grid_path, driver='GPKG')
    print('  {:,} populated hexagons saved: {}'.format(
        len(agg_gdf), os.path.basename(grid_path)))

    print('\nStep 4 - country-level summary...')
    grouped, _ = _summarise_by_country(agg_gdf, countries)

    csv_path = os.path.join(BASE_OUTPUT_DIR, 'country_summary.csv')
    grouped.to_csv(csv_path, index=False)
    print('  Saved: {}'.format(os.path.basename(csv_path)))

    countries_4326 = (
        countries.to_crs('EPSG:4326')[['name', 'geometry']]
        .rename(columns={'name': 'Country'})
    )
    gpkg_path = os.path.join(BASE_OUTPUT_DIR, 'country_summary.gpkg')
    gpd.GeoDataFrame(
        grouped.merge(countries_4326, on='Country', how='left'),
        crs='EPSG:4326',
    ).to_file(gpkg_path, driver='GPKG')
    print('  Saved: {}'.format(os.path.basename(gpkg_path)))

    _print_summary(agg_gdf, grouped)
    print('\nDone in {:.2f} minutes'.format((time.time() - t0) / 60))
