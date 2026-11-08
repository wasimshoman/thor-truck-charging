# thor-truck-charging

This repository estimates how many fast-charging points long-haul battery-electric trucks will need across Europe in 2030, and tests how that number changes when five design assumptions change. It contains the code, the input demand per map cell, and the results as GIS layers and CSV files.

It accompanies the paper Shoman et al. (under review) on design choices for truck charging networks. It reproduces that paper's sensitivity analysis only. Cost, land use and electricity prices are not included.

## 1. What the analysis does

THOR (Transport and Heavy-duty vehicle for Optimization and Resilience) is a model that:

1. estimates where long-haul trucks stop, using European road freight flows;
2. aggregates break stops within each hexagonal map cell;
3. estimates how many fast-charging points each cell needs, using a queueing model.

This repository starts at step 3. Its input is the daily number of break stops in each hexagon (`data/input/charging_demand_hexagons.gpkg`). From that input it reproduces:

- the baseline charging network;
- five sensitivity analyses, one per design assumption;
- peak-hour performance of the baseline network;
- a sensitivity index per country.

Steps 1 and 2 are included in `thor/pipeline/` as documentation, but are not run, because they need freight-flow data that this repository does not redistribute (section 6).

## 2. Quick start

```
conda env create -f environment.yml
conda activate thor-truck-charging
python scripts/run_all.py
```

The run takes about 3.5 minutes on a laptop. It writes `results/` and prints a table of 139 checks against the paper and the original notebook; the expected outcome is 139 PASS and 0 FAIL. The same table is saved as `results/acceptance_checks.csv`.

To test only the queueing module: `python thor/queueing.py`.

## 3. Method

### 3.1 From freight flows to daily charging demand

This part was run by the upstream pipeline (`thor/pipeline/`) and is not rerun here.

1. Each long-haul truck flow (longer than 200 km, more than 50 tonnes per year) is traced along the road network, with a route point every 10 km.
2. EU driving rules (Regulation (EC) No 561/2006) are applied: a break of at least 45 minutes after 4.5 hours of driving, and a 9-hour rest after the daily driving limit.
3. Each stop is classified as a break stop, which is a candidate for fast charging, or a rest stop (overnight, lower power).
4. Energy per stop is computed from the distance driven: 1.2 kWh/km below 80 km/h, and 1.8 kWh/km at or above 80 km/h.
5. Stops are summed per H3 hexagon (resolution 5, about 609 km²) and converted to daily values, using 300 working days per year and 13.6 tonnes of payload per truck. Each country has its own 2030 battery-electric share of the truck stock (`data/input/bet_share_by_country.csv`).

The result is $D$, the daily number of battery-electric break stops in each hexagon.

### 3.2 From charging demand to charging-point requirements

Each hexagon is treated as one charging area with a shared queue. Trucks on a mandatory break arrive; the charging points serve them. In queueing terms, the charging points are the "servers".

The symbols are:

- $D$: daily break stops in the hexagon (trucks per day).
- $\lambda$: arrival rate (trucks per hour). At baseline, $\lambda = 0.06\,D$, which spreads the daily stops evenly over a 16.7-hour driving day.
- $\mu$: trucks served per hour by one charging point. A 30-minute session gives $\mu = 2$.
- $c$: number of charging points in the hexagon.
- $\rho = \lambda / (c\mu)$: utilisation, the share of time an average charging point is busy. The queue only settles to a stable state if $\rho < 1$.
- $C_s^2$: the variance of the session duration divided by its mean squared. With a 5-minute standard deviation around 30 minutes, $C_s^2 = (5/30)^2 = 1/36$.
- $C_a^2$: the same measure for the time between arrivals. Fully random (Poisson) arrivals have $C_a^2 = 1$.
- $W_q$: estimated mean waiting time before charging starts.

The mean waiting time uses the Allen-Cunneen approximation:

$$W_q \approx W_q^{M/M/c}\,\frac{C_a^2 + C_s^2}{2}$$

Here $W_q^{M/M/c}$ is the exact mean wait (Erlang-C formula) for a queue with Poisson arrivals and exponentially distributed service times. At baseline ($C_a^2 = 1$) the model is an M/G/c queue. When $C_a^2 \neq 1$ (section 4), arrivals are no longer Poisson and the model is a G/G/c queue; Allen-Cunneen is the standard approximation for that case too.

The model selects the smallest number of charging points $c^*$ that keeps the estimated mean waiting time at or below 5 minutes and the utilisation at or below 0.95. The 5-minute target applies to the mean; individual trucks can wait longer.

Implementation: for each $c = 1, \dots, 120$ the code finds the largest $\lambda$ that meets both limits (bisection, tolerance $10^{-8}$) and then looks up $c^*$ for each hexagon. Arrival variability is run through the same table by setting $C_{s,\rm eff}^2 = C_a^2 + C_s^2 - 1$, because the formula depends only on the sum $C_a^2 + C_s^2$.

Charging power does not enter the queueing model; only the session duration does. The 30-minute session corresponds to an assumed charging power of about 1,100 kW (Megawatt Charging System; Shoman et al., 2023). This is consistent with the model's mean energy per break stop of 562 kWh delivered in 30 minutes.

### 3.3 Design assumptions tested

Each assumption is changed one at a time, with all others at baseline (section 4). The peak factor $p$ is the arrival rate in the busiest hour divided by the 24-hour average. Sizing for the busiest hour uses $\lambda = D\,p/24$. The baseline rule ($\lambda = 0.06\,D$) is equivalent to $p = 1.44$.

### 3.4 Peak-hour performance

The repository reports two different peak-hour analyses:

- **Resizing analysis:** how many charging points are needed if each hexagon is sized for the busiest hour? At $p = 1.666$ the answer is 806 more points than at baseline.
- **Fixed-infrastructure analysis:** what happens in the busiest hour if the baseline number of charging points is not changed? Each hexagon is classified as:
  - saturated ($\rho \ge 1$);
  - near-saturated ($0.95 \le \rho < 1$);
  - degraded (stable, but the estimated mean wait is above 5 minutes);
  - service OK.

The service failures in section 5 come from the fixed-infrastructure analysis. They describe the baseline network, not a network with the 806 extra points.

Waiting times in the fixed-infrastructure analysis are capped at 60 minutes for reporting. A saturated hexagon has no finite steady-state mean wait (its queue keeps growing while the peak lasts), so it is assigned 60 minutes as a placeholder. The 60-minute value is not a predicted maximum wait.

Code: `thor/queueing.py` (waiting time, lookup table, sizing), `thor/sensitivity.py` (sensitivity analyses, peak-hour metrics, country indices), `thor/data.py` (loading and study-area filter), `scripts/run_all.py`.

## 4. The five design choices

| Design choice | Baseline | Range tested | Basis for the tested values |
|---|---|---|---|
| Mean waiting-time target | 5 min | 3, 5, 10, 15, 20, 30 min | modelling assumption, spanning strict to relaxed service levels |
| Utilisation cap | 0.95 | 0.50 to 0.99 | modelling assumption, spanning a large reserve to almost none |
| Temporal peak factor | 1.44 (arrivals spread evenly over the driving day) | 1.0 to 2.0 | measured motorway truck counts: German 1.45, Swedish 1.666 |
| Arrival variability $C_a^2$ | 1 (Poisson) | 1, 1.5, 2, 3 | no European arrival data available; range is a modelling assumption |
| Session duration | 30 min | 15, 20, 30, 45, 60 min | about 60 min with current chargers, down to 15 min with future chargers |

The 45-minute case uses $\mu = 1.33$ per hour. This rounded value was kept from the original notebook so the results match it; the exact value is $4/3 \approx 1.333$.

Peak factors tested: 1.0, 1.2, 1.4, 1.44, 1.45, 1.6, 1.666, 1.691, 1.8, 2.0.

## 5. Results

Study area: 6,283 hexagons and 11,877 fast-charging points at baseline. Hexagons in Russia and Turkey are excluded. For how the study area is defined and how it differs from an earlier notebook version (11,878 points), see [docs/FILTER_HISTORY.md](docs/FILTER_HISTORY.md).

| Result | Value | File | Paper |
|---|---|---|---|
| Waiting-time target 3 / 30 min | +8.0% / −18.0% | `results/csv/sensitivity_wq.csv`, layer `sensitivity_wq` | Section 5.2, Figure 2a |
| Utilisation cap 0.50; 0.95 or higher | +14.3%; 0% | `sensitivity_rho` | Section 5.3, Figure 2b |
| Arrival variability 1.5 / 2 / 3 | +6.2% / +10.9% / +18.0% | `sensitivity_ca2` | Section 5.5, Figure 3a |
| Resizing for peak factor 1.666 | +806 points (+6.8%) | `sensitivity_peak_factor` | Section 5.6, Figure 3b |
| Fixed infrastructure at 1.666: classes | 7 saturated / 11 near-saturated / 761 degraded / 5,504 service OK | `baseline_hexagons`, `busy_hour_failures`, `saturated_areas`, `csv/peak_factor_tiers.csv` | Section 5.6, Appendix D |
| Fixed infrastructure at 1.666: hexagons that do not meet the peak-hour service criteria | 779 hexagons (12.4%), receiving 47.2% of busy-hour truck arrivals | `csv/peak_factor_ops.csv` | Section 5.6, Figure 4 |
| Session duration 15 / 60 min | −28.7% / +54.9% | `sensitivity_service_time` | Section 5.8 |
| Service variability (grid at three $C_s^2$ values) | −48 points (constant session, $C_s^2 = 0$) and +1,259 points (exponential sessions, $C_s^2 = 1$) | `csv/joint_grid_wq_rho_cs2.csv` | Section 5.4 |
| Country indices | `S_wq`, `S_rho` per country; median 0.241 and 0.029 | `country_totals` | Section 5.7, Appendix E |

The 47.2% is the share of busy-hour truck arrivals (equivalently, of daily break-stop demand) that falls in the 779 hexagons. The paper reports the same number as "share of peak truck-hours".

The totals of all five analyses are in `results/csv/sensitivity_totals.csv`. Column definitions for every file are in [docs/COLUMNS.md](docs/COLUMNS.md).

Not reproduced: the 0.22% interaction between the waiting-time target and the utilisation cap (paper Section 5.4). The joint grid is included, but the step that computes this value from it was not part of the extracted code.

`scripts/run_all.py` regenerates `results/thor_results.gpkg`. The reproduced data are equivalent, but the GeoPackage files may not be byte-for-byte identical.

## 6. Data

| Input | Source | Licence | In this repository |
|---|---|---|---|
| `data/input/charging_demand_hexagons.gpkg` | THOR output (pipeline script 03), trimmed to the columns the model uses | CC BY 4.0 | yes |
| `data/input/countries.gpkg` | Country polygons used for the study-area filter (EU and neighbours, with Turkey) | see source file | yes, attributes `name` and `iso3` only |
| `data/input/bet_share_by_country.csv` | Battery-electric share of the truck stock per country, 2030, medium scenario, mean of four segments; from the vesuvio project parameters (Shoman et al., 2023) | CC BY 4.0 | yes |
| `data/reference/*.csv` | Output files of the original notebook, used only to check this code | CC BY 4.0 | yes |
| Stop-event file (about 1 million points, 900 MB) | Output of pipeline scripts 01 and 02 | CC BY 4.0 | no; not yet deposited |
| Freight-flow data | Speth, D., Sauter, V., Plötz, P., Signer, T., 2022. Synthetic European road freight transport flow data. Data in Brief 40, 107786. https://doi.org/10.1016/j.dib.2021.107786 (data: https://data.mendeley.com/datasets/py2zkrb65h/1) | see source | no; download from the source |

`scripts/prepare_inputs.py` rebuilds `data/input/` from the author's working files. It is not needed to reproduce the results.

## 7. Limitations

From paper Section 6.3:

- The peak-factor analysis keeps the shape of the Swedish daily profile and only scales its height.
- Waiting times use a steady-state formula for each hour; queues carried over from one hour to the next are not modelled.
- Modelled truck flows stand in for observed charging demand.
- Hexagons are evaluated independently; the analysis does not represent trucks choosing to charge in neighbouring cells.
- Session duration equals the time a charging point is occupied. In practice, a truck on a 45-minute break may hold the point longer than its charging session.
- No European data on truck arrival patterns at chargers exist, so the Poisson baseline is untested.
- Results are point estimates, without confidence intervals.
- Queues have no length limit. Limiting the queue to 10 waiting trucks adds 8.8% more charging points.

## 8. Citation, funding, licence, contact

Citation: see `CITATION.cff`. Cite the paper as Shoman et al., under review.

Funding: funded by the European Union (Horizon Europe, MACBETH, grant agreement No 101192466). Views and opinions expressed are those of the author(s) only and do not necessarily reflect those of the European Union or the European Climate, Infrastructure and Environment Executive Agency (CINEA). Neither the European Union nor the granting authority can be held responsible for them.

Licence: code MIT (`LICENSE`); data and results CC BY 4.0 (`LICENSE-data`).

Contact: Wasim Shoman, Chalmers Next Labs, shoman@chalmers.se.
