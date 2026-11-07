# thor-truck-charging

Code and results for the THOR model of fast-charging demand for long-haul battery-electric trucks in Europe in 2030, and for the design-choice sensitivity analysis in Shoman et al., under review ("Paper 1").

Only the sensitivity analysis of Paper 1 is reproduced here. Economics, land cost, electricity prices and slides are out of scope.

## 1. What THOR is and what this repository reproduces

THOR (Transport and Heavy-duty vehicle for Optimization and Resilience) turns a model of European road freight flows into stop events of long-haul trucks, adds up the break stops in each hexagonal map cell, and sizes the number of fast charging points each cell needs with a queueing model. One charging point serves one truck at a time for 30 minutes (about 1,100 kW).

This repository starts from the daily break-stop demand per hexagon (`data/input/charging_demand_hexagons.gpkg`). It reproduces the baseline network and the five sensitivity sweeps of the paper, the peak-hour operating metrics, and the country sensitivity indices, and writes them as GIS layers and CSV files in `results/`.

The earlier pipeline steps (route points, driving rules, stop events, aggregation) are in `thor/pipeline/` for documentation. They are not run, because they need the freight-flow data, which is not redistributed (section 6).

## 2. Quick start

```
conda env create -f environment.yml
conda activate thor-truck-charging
python scripts/run_all.py
```

Expected runtime: about 3.5 minutes on a laptop (the sweeps run once on the study-area filter and once on the earlier notebook filter, see section 5). The script writes `results/` and prints a PASS/FAIL table with 139 checks. Expected outcome: 139 PASS and 0 FAIL. The table is also saved as `results/acceptance_checks.csv`.

Quick self-check of the queueing module: `python thor/queueing.py`.

## 3. Method

**Pipeline.** (1) Each long-haul truck flow (more than 200 km, more than 50 tonnes per year) is traced along the road network and route points are placed every 10 km. (2) European driving rules (Regulation (EC) No 561/2006) are simulated: a break of at least 45 minutes after 4.5 hours of driving and a 9-hour rest after the daily driving limit. (3) Each stop is classified as a break stop (candidate for fast charging) or a rest stop (overnight, lower power). (4) Energy per stop follows from distance driven and a speed-dependent rate (1.2 kWh/km below 80 km/h, 1.8 kWh/km at or above). (5) Stops are summed per H3 hexagon (resolution 5, about 609 km2) and converted to daily values with 300 working days per year and a payload of 13.6 tonnes per truck. Each country has its own 2030 battery-electric stock share (`data/input/bet_share_by_country.csv`). The quantity used here is the daily break-stop demand $D$ per hexagon.

**Queueing model.** Each hexagon is one multi-server queue. Trucks on a mandatory break are the arrivals. Charging points are the servers.

- $\lambda$ is the arrival rate in trucks per hour. At baseline $\lambda = 0.06\,D$ (daily demand spread evenly over the 16.7-hour driving window).
- $\mu = 2$ per hour is the number of trucks one charging point serves per hour (30-minute sessions).
- $c$ is the number of charging points. The utilisation $\rho = \lambda/(c\mu)$ is the share of time an average point is busy. The queue is stable only if $\rho < 1$.
- $C_s^2 = (5/30)^2 = 1/36$ is the squared coefficient of variation of the service time (its variance divided by its mean squared).
- $C_a^2$ is the same quantity for the times between arrivals. Poisson (random) arrivals have $C_a^2 = 1$.

The mean waiting time follows the Allen-Cunneen approximation:

$$W_q^{M/G/c} \approx W_q^{M/M/c}\,\frac{C_a^2 + C_s^2}{2}$$

where $W_q^{M/M/c}$ is the exact Erlang-C waiting time of the equivalent queue with random service. Each hexagon gets the smallest $c^*$ with $W_q \le W_q^{\rm target}$ (5 minutes at baseline) and $\rho \le \rho_{\max}$ (0.95 at baseline). The code builds a table of the largest admissible $\lambda$ for $c = 1,\dots,120$ by bisection (tolerance $10^{-8}$) and looks up $c^*$. Arrival variability is run through the same table with the effective service variability $C_{s,\rm eff}^2 = C_a^2 + C_s^2 - 1$, because only the sum $C_a^2 + C_s^2$ enters the formula.

**Peak factor.** The peak factor $p$ is the arrival rate in the busiest hour divided by the 24-hour average. Sizing for the busiest hour uses $\lambda = D\,p/24$. The baseline convention ($\lambda = 0.06\,D$) equals $p = 1.44$. The busy-hour analysis keeps the baseline points fixed, applies $p = 1.666$ (Swedish motorway counts) and classes each hexagon as saturated ($\rho \ge 1$), near-saturated ($0.95 \le \rho < 1$), degraded (stable but waiting more than 5 minutes) or within standard. Reported waits are capped at 60 minutes.

Code: `thor/queueing.py` (waiting time, table, sizing), `thor/sensitivity.py` (sweeps, busy-hour metrics, country indices), `thor/data.py` (loading and study-area filter), `scripts/run_all.py`.

## 4. The five design choices

| Design choice | Baseline | Range tested | Real-world anchor (paper Table 2) |
|---|---|---|---|
| Waiting-time standard | 5 min | 3, 5, 10, 15, 20, 30 min | industry convention |
| Utilisation cap | 0.95 | 0.50 to 0.99 | resilience guidelines |
| Temporal peak factor | 1.44 (flat arrival distribution) | 1.0 to 2.0 | German 1.45; Swedish 1.666 |
| Arrival variability $C_a^2$ | 1 (Poisson) | 1, 1.5, 2, 3 | no EU dataset yet |
| Service duration | 30 min | 15, 20, 30, 45, 60 min | 60 min (today) to 15 min (future) |

The 45-minute case uses $\mu = 1.33$ per hour, as in the original notebook. Peak factors run at 1.0, 1.2, 1.4, 1.44, 1.45, 1.6, 1.666, 1.691, 1.8, 2.0.

## 5. Results

Study area: 6,283 hexagons, 11,877 fast charging points (hexagon centroids in EPSG:3035 joined within the country polygons, excluding Russia and Turkey and hexagons outside every polygon, with at least one point).

| Result | Value | File | Paper |
|---|---|---|---|
| Waiting-time standard 3 / 30 min | +8.0% / -18.0% | `results/csv/sensitivity_wq.csv`, layer `sensitivity_wq` | Section 5.2, Figure 2a |
| Utilisation cap 0.50; 0.95 or higher | +14.3%; 0% | `sensitivity_rho` | Section 5.3, Figure 2b |
| Arrival variability 1.5 / 2 / 3 | +6.2% / +10.9% / +18.0% | `sensitivity_ca2` | Section 5.5, Figure 3a |
| Peak factor 1.666 | +806 points (+6.8%) | `sensitivity_peak_factor` | Section 5.6, Figure 3b |
| Busy-hour tiers at 1.666 | 7 saturated / 11 near-saturated / 761 degraded / 5,504 within standard | `baseline_hexagons`, `busy_hour_failures`, `saturated_areas`, `csv/peak_factor_tiers.csv` | Section 5.6, Appendix D |
| Failing hexagons | 779 (12.4%), carrying 47.2% of busy-hour truck-hours | `csv/peak_factor_ops.csv` | Section 5.6, Figure 4 |
| Service duration 15 / 60 min | -28.7% / +54.9% | `sensitivity_service_time` | Section 5.8 |
| Country indices | `S_wq`, `S_rho` per country | `country_totals` | Section 5.7, Appendix E |
| Interaction of Wq and rho (grid at three $C_s^2$ values) | -48 (M/D/c) and +1,259 (exponential service) points | `csv/joint_grid_wq_rho_cs2.csv` | Section 5.4 |

The totals of all five sweeps are collected in `results/csv/sensitivity_totals.csv`.

**One study-area filter.** Every number in the paper and in this repository uses the filter in section 5: hexagon centroids computed in EPSG:3035, 6,283 hexagons, 11,877 points. All 39 section A checks in the table pass. An earlier version of the notebook computed centroids in EPSG:4326, which keeps one 2-point coastal hexagon that this filter drops and drops a 1-point hexagon that this filter keeps (11,878 points). Section B of the table reruns the sweeps on that earlier filter and reproduces the notebook's output files exactly (100 of 100 checks pass). It is a reproduction check only, not the filter of the paper.

The median country index $S_{\rho}$ is 0.029, about eight times smaller than the median $S_{W_q}$ (0.241).

The interaction value of 0.22% quoted in paper Section 5.4 is not reproduced, because the grid cell that defines it is not part of the extracted code.

The seven saturated hexagons are named from the paper (Appendix D), except three that were renamed from their coordinates: the cell at 53.38 N, 2.94 W is "Chester / Merseyside (UK)", the cell at 52.07 N, 0.78 W is "Milton Keynes (UK)", and the cell at 58.89 N, 14.50 E is "Laxå, Örebro / Västra Götaland border (SE)" (the paper called it Örebro–Värmland).

`results/thor_results.gpkg` is regenerated by `scripts/run_all.py`; its contents are reproducible but the file may differ byte by byte between runs.

## 6. Data

| Input | Source | Licence | In this repository |
|---|---|---|---|
| `data/input/charging_demand_hexagons.gpkg` | THOR output (script 03), columns trimmed to those the model uses | CC BY 4.0 | yes |
| `data/input/countries.gpkg` | Country polygons used for the study-area filter (EU plus neighbours, with Turkey) | see source file | yes, attributes `name`, `iso3` only |
| `data/input/bet_share_by_country.csv` | Country battery-electric truck stock shares 2030 (medium scenario, mean of four segments), from the vesuvio project parameters; Shoman et al. (2023) | CC BY 4.0 | yes |
| `data/reference/*.csv` | Output files of the notebook, used only to check this code (section B of the check table) | CC BY 4.0 | yes |
| Stop-event file (about 1 million points, 900 MB) | Output of pipeline scripts 01 and 02 | CC BY 4.0 | no; to be deposited on Zenodo, DOI `10.5281/zenodo.XXXXXXX` (placeholder) |
| Freight-flow data | Speth, D., Sauter, V., Plötz, P., Signer, T., 2022. Synthetic European road freight transport flow data. Data in Brief 40, 107786. https://doi.org/10.1016/j.dib.2021.107786 (data: https://data.mendeley.com/datasets/py2zkrb65h/1) | see source | no; download from the source |

`data/input/` is rebuilt from the author's working files with `scripts/prepare_inputs.py`. This is not needed for reproduction.

## 7. Column dictionaries

Hexagon identifiers (`h3_id`) are H3 resolution-5 cell indices computed from the hexagon centroid. In the CSV files `lon` and `lat` are the hexagon centroid in degrees (EPSG:4326). Points are fast 30-minute charging points. "Busy hour" means the peak hour at peak factor 1.666 with the baseline points kept fixed.

**data/input/charging_demand_hexagons.gpkg** (EPSG:4326, 7,519 hexagons)

| Column | Meaning | Unit | Source |
|---|---|---|---|
| h3_id | H3 cell index, resolution 5 | text | computed from centroid |
| MDTN_B_CouSha | Daily break-stop demand D (country-specific battery-electric share) | trucks per day | THOR script 03 |
| NFCh30m_CouSha | Baseline fast 30-minute charging points | count | THOR script 03 |

**data/input/countries.gpkg** (EPSG:4326): `name` country name; `iso3` ISO 3166 alpha-3 code. Source: country boundary file used in the original work.

**data/input/bet_share_by_country.csv**: `country_iso2` ISO alpha-2 code (the file uses UK, not GB); `bet_share_2030` battery-electric share of the truck stock in 2030 (fraction). Source: vesuvio parameters, sheet `bet_stock_share`.

**data/reference/**: `wq_sensitivity.csv`, `rho_sensitivity.csv`, `ca2_sensitivity.csv`, `peak_factor_ops.csv`, `peak_factor_tiers.csv`. Columns as in the matching `results/csv` tables; they hold notebook outputs on the notebook filter (11,878 points).

**results/thor_results.gpkg** layers (EPSG:4326) and the same tables in `results/csv/` (CSV has `lon`, `lat` in place of geometry)

`baseline_hexagons` and `busy_hour_failures` (the 779 hexagons whose tier is not "Service OK") and `saturated_areas` (the 7 hexagons with tier "Saturated"; extra column `name`):

| Column | Meaning | Unit | Source |
|---|---|---|---|
| h3_id | H3 cell index | text | input |
| country | Country of the hexagon centroid | text | spatial join |
| daily_stops | Daily break-stop demand D | trucks per day | input |
| lambda_per_h | Baseline arrival rate, 0.06 x D | trucks per hour | computed |
| points | Baseline charging points | count | input |
| busy_rho | Busy-hour utilisation with baseline points | ratio | computed |
| busy_wait_min | Busy-hour mean waiting time, capped at 60 | minutes | computed |
| busy_tier | Saturated, Near-saturated, Degraded or Service OK | text | computed |
| name | Place name from the paper (`saturated_areas` only) | text | paper Appendix D |

`sensitivity_wq`, `sensitivity_rho`, `sensitivity_ca2`, `sensitivity_peak_factor`, `sensitivity_service_time` hold `h3_id`, `country` and one column of charging points (count) per tested value: `wq_<minutes>`, `rho_<percent>` (for example `rho_95` is 0.95), `ca2_<value>` (`1p5` is 1.5), `p_<peak factor>` (`1p666` is 1.666), `svc_<minutes>`.

`country_totals` (country polygons; CSV `country_totals.csv` is the same table without geometry, same column names and order): `country`, `iso3`, `baseline_points` (count; this is the `wq_5` total), the other sweep columns as above summed over the country (count), `lambda_per_h` (sum, trucks per hour), `S_wq` and `S_rho` (index: largest minus smallest total across the waiting-time or utilisation sweep, divided by the baseline total; countries with fewer than 20 baseline points are dropped), `n_hexagons`.

`results/csv/sensitivity_totals.csv`: `choice`, `scenario`, `points`, `delta` (points minus baseline), `pct` (percent change). `peak_factor_ops.csv`: `peak`, `failed_pct_count` and `failed_pct_demand` (percent of hexagons and of busy-hour truck-hours below standard), `wq_dw_min` (demand-weighted wait, minutes), `rho_dw` (demand-weighted utilisation), `n_saturated`. `peak_factor_tiers.csv`: `peak` and, for each tier `<tier>_n` (hexagons), `_pct` (percent of hexagons), `_dem` (percent of demand), plus `bays_needed`, `extra_bays`, `extra_pct` (points needed to restore full compliance and the difference to baseline). `joint_grid_wq_rho_cs2.csv`: `Cs2`, `Wq_min`, `rho_max`, `points`. `results/acceptance_checks.csv`: `section`, `check`, `expected`, `got`, `status`, `cause if FAIL`.

## 8. Limitations, citation, funding, licence, contact

Limitations (paper Section 6.3, short): the peak-factor deformation keeps the Swedish profile shape; waiting times use a steady-state formula for each hour; modelled truck flows stand in for charging demand; hexagons are evaluated independently, so busy-hour failure shares are upper bounds; service time equals session time; Poisson arrivals are untested because no European arrival data exist; results are point estimates; the queue is unbounded (a finite-buffer check gives +8.8%).

Citation: see `CITATION.cff`. Cite the paper as Shoman et al., under review.

Funding: funded by the European Union (Horizon Europe, MACBETH, grant agreement No 101192466). Views and opinions expressed are those of the author(s) only and do not necessarily reflect those of the European Union or the European Climate, Infrastructure and Environment Executive Agency (CINEA). Neither the European Union nor the granting authority can be held responsible for them.

Licence: code MIT (`LICENSE`); data and results CC BY 4.0 (`LICENSE-data`).

Contact: Wasim Shoman, Chalmers Next Labs, shoman@chalmers.se.
