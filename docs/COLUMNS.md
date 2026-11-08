# Column dictionaries

Hexagon identifiers (`h3_id`) are H3 resolution-5 cell indices computed from the hexagon centroid. In the CSV files, `lon` and `lat` give the hexagon centroid in degrees (EPSG:4326). All counts are fast 30-minute charging points. Some column names say "bays"; a bay means one charging point.

"Busy hour" means the peak hour at peak factor 1.666, with the baseline number of charging points kept unchanged (the fixed-infrastructure analysis in README section 3.4).

## Inputs

**data/input/charging_demand_hexagons.gpkg** (EPSG:4326, 7,519 hexagons)

| Column | Meaning | Unit | Source |
|---|---|---|---|
| h3_id | H3 cell index, resolution 5 | text | computed from centroid |
| MDTN_B_CouSha | Daily break-stop demand D (country-specific battery-electric share) | trucks per day | THOR script 03 |
| NFCh30m_CouSha | Baseline fast 30-minute charging points | count | THOR script 03 |

**data/input/countries.gpkg** (EPSG:4326): `name` country name; `iso3` ISO 3166 alpha-3 code. Source: the country boundary file used in the original work.

**data/input/bet_share_by_country.csv**: `country_iso2` ISO alpha-2 code (the file uses UK, not GB); `bet_share_2030` battery-electric share of the truck stock in 2030 (fraction). Source: vesuvio project parameters, sheet `bet_stock_share`.

**data/reference/**: `wq_sensitivity.csv`, `rho_sensitivity.csv`, `ca2_sensitivity.csv`, `peak_factor_ops.csv`, `peak_factor_tiers.csv`. Output files of the original notebook, computed on the earlier filter (11,878 points; see [FILTER_HISTORY.md](FILTER_HISTORY.md)). Columns as in the matching `results/csv` tables.

## Results

`results/thor_results.gpkg` (EPSG:4326). The same tables are in `results/csv/`, where `lon` and `lat` replace the geometry.

**`baseline_hexagons`**, **`busy_hour_failures`** (the 779 hexagons whose tier is not "Service OK") and **`saturated_areas`** (the 7 hexagons with tier "Saturated"; extra column `name`):

| Column | Meaning | Unit | Source |
|---|---|---|---|
| h3_id | H3 cell index | text | input |
| country | Country of the hexagon centroid | text | spatial join |
| daily_stops | Daily break-stop demand D | trucks per day | input |
| lambda_per_h | Baseline arrival rate, 0.06 × D | trucks per hour | computed |
| points | Baseline charging points | count | input |
| busy_rho | Busy-hour utilisation with baseline points | ratio | computed |
| busy_wait_min | Busy-hour estimated mean waiting time. Reporting cap: values above 60 are set to 60, and saturated hexagons (no finite mean exists) are set to 60 as a placeholder. Not a predicted maximum wait. | minutes | computed |
| busy_tier | Saturated, Near-saturated, Degraded or Service OK | text | computed |
| name | Place name (`saturated_areas` only) | text | paper Appendix D, corrected from coordinates |

**`sensitivity_wq`, `sensitivity_rho`, `sensitivity_ca2`, `sensitivity_peak_factor`, `sensitivity_service_time`**: `h3_id`, `country`, and one column of charging points (count) per tested value: `wq_<minutes>`, `rho_<percent>` (`rho_95` is 0.95), `ca2_<value>` (`1p5` is 1.5), `p_<peak factor>` (`1p666` is 1.666), `svc_<minutes>`.

**`country_totals`** (country polygons; `country_totals.csv` is the same table without geometry, same columns in the same order): `country`, `iso3`, `baseline_points` (count; equal to the `wq_5` total), the other sweep columns summed over the country (count), `lambda_per_h` (sum, trucks per hour), `S_wq` and `S_rho`, `n_hexagons`. `S_wq` and `S_rho` are the largest minus the smallest country total across the waiting-time or utilisation sweep, divided by the baseline total. Countries with fewer than 20 baseline points are left out.

**`results/csv/sensitivity_totals.csv`**: `choice`, `scenario`, `points`, `delta` (points minus baseline), `pct` (percent change).

**`peak_factor_ops.csv`** (fixed-infrastructure analysis, one row per peak factor):

| Column | Meaning | Unit |
|---|---|---|
| peak | Peak factor p | ratio |
| failed_pct_count | Share of hexagons that do not meet the busy-hour service criteria | percent of hexagons |
| failed_pct_demand | Share of busy-hour truck arrivals that occur in those hexagons. Busy-hour arrivals are D × p / 24, so this equals the share of daily break-stop demand D. The paper calls it "share of peak truck-hours". | percent of arrivals |
| wq_dw_min | Mean waiting time weighted by D, using the capped waits | minutes |
| rho_dw | Utilisation weighted by D, capped at 1 | ratio |
| n_saturated | Hexagons with utilisation at or above 1 | count |

**`peak_factor_tiers.csv`**: `peak`; for each tier, `<tier>_n` (hexagons), `<tier>_pct` (percent of hexagons), `<tier>_dem` (percent of busy-hour arrivals); plus `bays_needed`, `extra_bays`, `extra_pct` (charging points needed under the resizing analysis, and their difference from the baseline).

**`joint_grid_wq_rho_cs2.csv`**: `Cs2`, `Wq_min`, `rho_max`, `points`.

**`results/acceptance_checks.csv`**: `section`, `check`, `expected`, `got`, `status`, `cause if FAIL`.
