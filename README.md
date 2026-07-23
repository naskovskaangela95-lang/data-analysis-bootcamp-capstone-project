# Capstone Project: Public Transport Ridership Analytics

## Scenario

You've joined the analytics team at **CityTransit**, the municipal public transport authority. The agency runs buses, trams, and a metro line across the city. Data sits in four separate exports that nobody has ever brought together: ticket validations from the fare gates, route master data, vehicle fleet records, and a stops registry.

Management wants a dashboard answering: which routes are overloaded, when are the peak hours, how does ridership vary by fare type and district, and which vehicles are underutilised. Your job is to build the analysis in Jupyter notebooks and hand off clean aggregate tables that Power BI can consume.

---

## Getting Started (Fork & Clone)

Work on your own copy of the repository so your commits stay separate from the instructor's original.

1. **Fork the repo.** Open the project on GitHub and click **Fork** (top-right). Choose your own account as the owner. GitHub creates a copy at `https://github.com/<your-username>/trafic-capstone-project`.

2. **Clone your fork locally.** Copy the URL from the green **Code** button on *your* fork, then:

   ```bash
   # HTTPS
   git clone https://github.com/<your-username>/trafic-capstone-project.git

   
   ```

4. **Install dependencies:** (Optional)

   ```bash
   
   pip install numpy pandas faker
   ```


---

## Input Data

Four CSV files in `data/raw/`:

| File | Approx. rows | Description |
|---|---|---|
| `validations.csv` | ~80,000 | One row per ticket validation (boarding) |
| `routes.csv` | ~60 | Route master data |
| `vehicles.csv` | ~180 | Fleet records |
| `stops.csv` | ~400 | Stop registry |

### `validations.csv`
| Column | Type | Notes |
|---|---|---|
| `validation_id` | string | Format `VAL-0001234`; contains duplicates |
| `validation_ts` | string | **Mixed formats**: `2024-03-15 07:42:11`, `15/03/2024 07:42`, `March 15, 2024 7:42 AM` |
| `route_id` | string | FK to routes; some have trailing whitespace |
| `vehicle_id` | string | FK to vehicles |
| `stop_id` | string | FK to stops |
| `card_id` | string | Anonymised card; ~12% blank (single-ride paper ticket) |
| `fare_type` | string | Inconsistent casing: `Adult`, `adult`, `ADULT`, `Full Fare` |
| `fare_amount` | float | Some nulls, a few absurd values (`9999.0`) |
| `passenger_count` | int | Usually 1; some nulls, a few negatives (failed/reversed validations) |
| `transfer_flag` | mixed | `Y`/`N`/`1`/`0`/`TRUE`/`FALSE` — needs normalising |

### `routes.csv`
| Column | Type | Notes |
|---|---|---|
| `route_id` | string | Primary key |
| `route_name` | string | Leading/trailing whitespace |
| `mode` | string | Inconsistent: `Bus`, `bus`, `BUS `, `Tram`, `Metro` |
| `district` | string | Some nulls |
| `route_length_km` | float | Some nulls |
| `scheduled_trips_per_day` | int | |

### `vehicles.csv`
| Column | Type | Notes |
|---|---|---|
| `vehicle_id` | string | Primary key |
| `vehicle_type` | string | `Standard Bus`, `Articulated Bus`, `Tram`, `Metro Set` |
| `capacity` | int | Some nulls |
| `year_manufactured` | int | Some impossible values (`1899`, `2035`) |
| `depot` | string | |

### `stops.csv`
| Column | Type | Notes |
|---|---|---|
| `stop_id` | string | Primary key |
| `stop_name` | string | Whitespace and casing issues |
| `district` | string | |
| `zone` | string | `Zone 1`, `Zone 2`, `Zone 3` |
| `has_shelter` | mixed | `Y`/`N`/`1`/`0` |

---

## Notebook Structure

Students work entirely in notebooks. Five notebooks, run in order.

```
trafic-capstone-project/
├── data/
│   ├── raw/
│   ├── processed/
│   └── rejects/
├── notebooks/
│   ├── 01_ingest_and_profile.ipynb
│   ├── 02_clean.ipynb
│   ├── 03_join_and_explore.ipynb
│   ├── 04_aggregate_and_export.ipynb
│   └── 05_database_bonus.ipynb
├── sql/
│   └── schema.sql          # bonus only
├── requirements.txt
├── README.md
└── report.pbix
```

Each notebook must end by saving its output to folder so the next notebook can pick up where the previous one left off. 
---

## Notebook 01 — Ingestion & Profiling

1. Read all four CSVs with explicit `dtype` specification — IDs must stay strings, not become floats.
2. Handle the missing-file case with a clear message rather than a raw traceback.
3. For each file, produce a profile: row count, column count, dtypes, null counts and null percentages per column, memory usage, and `.head()`.
4. For every categorical column, print `value_counts()` and write one markdown cell noting what looks wrong.
5. Save the raw frames to `data/interim/` unchanged.

Every code cell must be preceded or followed by a markdown cell explaining what you found — not what the code does.

---

## Notebook 02 — Cleaning & Preparation

Implement each rule as its own function defined in a cell, then apply it. Keep a running counter of rows dropped and why.

### Validations
- Drop exact duplicates and duplicate `validation_id` (keep first).
- Parse `validation_ts` into a real `datetime64` column handling all three formats. Unparseable rows go to `data/rejects/`.
- Strip whitespace from all ID columns.
- Normalise `fare_type` to a fixed set: `Adult`, `Student`, `Senior`, `Child`, `Pass Holder`.
- Normalise `transfer_flag` to a proper boolean.
- Handle `passenger_count`: nulls → drop and log; negatives → keep but add `is_reversed` boolean.
- Handle `fare_amount`: nulls → impute with the median for that `fare_type`; values above the 99.5th percentile → cap at that percentile. Justify the choice in markdown.
- Replace blank `card_id` with `SINGLE_RIDE`.

### Routes
- Trim and title-case `route_name`.
- Standardise `mode` to Title Case, stripped.
- Fill null `district` with `Unknown`.
- Fill null `route_length_km` with the median for that `mode`.

### Vehicles
- Set `year_manufactured` outside `[1980, 2026]` to null.
- Derive `vehicle_age_band`: `0-5`, `6-10`, `11-20`, `20+`, `Unknown`.
- Fill null `capacity` with the median for that `vehicle_type`.

### Stops
- Trim and title-case `stop_name`.
- Normalise `has_shelter` to boolean.

### Referential integrity
Report and drop validations whose `route_id`, `vehicle_id`, or `stop_id` doesn't exist in the master files. Validations with `card_id = 'SINGLE_RIDE'` are valid and must be kept.

### Derived columns
On validations:
- `date`, `year`, `month`, `year_month` (`YYYY-MM`), `quarter`
- `hour` (0–23)
- `day_of_week`, `is_weekend`
- `time_period`: `Early (04-06)`, `AM Peak (07-09)`, `Midday (10-15)`, `PM Peak (16-18)`, `Evening (19-23)`, `Night (00-03)`
- `revenue = fare_amount * passenger_count`

Save cleaned frames to `data/interim/` and every dropped row to `data/rejects/` with a `reject_reason` column.

---

## Notebook 03 — Joining & Exploration

1. Build a single fact table by joining validations → routes → vehicles → stops.
2. Choose join types deliberately and justify each in markdown.
3. Assert that the row count after joining equals the cleaned validation count. Fail loudly if it doesn't — a silent fan-out is the classic bug here.
4. Derive `load_factor = passenger_count / capacity` at vehicle-trip level where meaningful.
5. Produce at least six exploratory charts with matplotlib or seaborn: hourly ridership curve, weekday vs weekend comparison, ridership by mode, fare type mix, top routes, district distribution.
6. Write a markdown summary of three things you learned that you didn't expect.

Save the fact table to `data/interim/fact_validations.parquet`.

---

## Notebook 04 — Aggregation & Export

Build these tables, each written to `data/processed/<name>.csv`.

| # | Table | Grain | Measures |
|---|---|---|---|
| 1 | `agg_ridership_by_month` | `year_month` | total_boardings, total_revenue, unique_cards, avg_daily_boardings |
| 2 | `agg_ridership_by_hour` | `hour`, `day_type` (weekday/weekend) | total_boardings, avg_boardings_per_day, pct_of_daily_total |
| 3 | `agg_route_performance` | `route_id`, `route_name`, `mode`, `district`, `year_month` | total_boardings, total_revenue, boardings_per_km, avg_load_factor |
| 4 | `agg_mode_summary` | `mode`, `year_month` | total_boardings, total_revenue, route_count, boardings_per_route |
| 5 | `agg_fare_type_mix` | `fare_type`, `year_month` | boardings, revenue, pct_of_monthly_boardings |
| 6 | `agg_stop_activity` | `stop_id`, `stop_name`, `district`, `zone` | total_boardings, rank_within_district, has_shelter |
| 7 | `agg_vehicle_utilisation` | `vehicle_id`, `vehicle_type`, `depot`, `vehicle_age_band` | total_boardings, avg_load_factor, active_days |
| 8 | `agg_peak_analysis` | `time_period`, `mode` | total_boardings, avg_load_factor, pct_of_mode_total |
| 9 | `agg_transfer_behaviour` | `year_month`, `mode` | transfer_count, transfer_rate |

Requirements:
- Use `groupby().agg()` with named aggregations, not chained `.sum()` calls.
- At least three tables must use a window operation via `transform` — the `pct_of_*` columns and month-over-month growth.
- Round monetary values to 2 decimals, rates to 4.
- Sort each output sensibly.
- No nulls allowed in key columns — assert this before writing.
- Write `_manifest.csv` listing each output file, row count, column count, and generation timestamp.
- Use `index=False`, UTF-8, ISO dates so Power BI parses cleanly.

---

## Power BI Report

Import from `data/processed/` and build at least three pages.

**Page 1 — Network Overview**
KPI cards (total boardings, total revenue, unique cards, avg load factor), monthly ridership trend, boardings by mode, boardings by district.

**Page 2 — Time & Demand Patterns**
Hourly ridership curve split by weekday/weekend, peak period breakdown, transfer rate trend, fare type mix over time.

**Page 3 — Routes, Stops & Fleet**
Top 15 routes leaderboard, boardings per km scatter, stop activity table with zone filter, vehicle utilisation by age band and depot.

Requirements:
- A date slicer synced across all pages.
- Consistent formatting — currency, percentages, one coherent colour theme.
- One paragraph of written insight per page describing what the data actually shows and what you'd recommend to the agency.

---

## Notebook 05 — Bonus: Database Sink

Instead of leaving the aggregates as CSVs, persist them to a database and point Power BI at that instead.

### Option A — SQLite

1. Create `data/warehouse.db` with `sqlite3` or SQLAlchemy.
2. Write explicit DDL in `sql/schema.sql` — real types, primary keys, `NOT NULL` on key columns. Don't rely on `to_sql` inferring the schema for you.
3. Make loads idempotent: rerunning the notebook must not duplicate rows. Either truncate-and-reload or upsert with `INSERT ... ON CONFLICT DO UPDATE`.
4. Wrap each table load in a transaction and roll back on error.
5. Add indexes on the columns Power BI will filter on: `year_month`, `mode`, `district`.
6. Add a `pipeline_runs` audit table: run id, start time, end time, rows written per table, status.
7. Verify by querying the database back into pandas and comparing row counts against the CSVs.
8. Connect Power BI via the SQLite ODBC driver and rebuild one report page from database tables.

### Option B — PostgreSQL

Everything above, plus:

1. Use SQLAlchemy with `psycopg2`, reading connection details from environment variables or a `.env` file. No credentials in the notebook — and make sure `.env` is git-ignored.
2. Create a dedicated `analytics` schema.
3. Use proper types: `NUMERIC(12,2)` for money, `DATE`, `VARCHAR(n)` — not `TEXT` for everything.
4. Implement upserts via `ON CONFLICT` on declared primary keys.
5. Create at least one SQL view combining two aggregate tables — for example route performance joined to mode summary — and point one Power BI visual at the view.
6. Try both Import and DirectQuery mode in Power BI and write a short paragraph on which you'd choose here and why.

---

## Deliverables

- Five notebooks, all cells executed top to bottom with output visible, no errors.
- `data/processed/` with all nine aggregate CSVs plus the manifest.
- `data/rejects/` with every dropped row and its reason.
- `report.pbix`.
- `sql/schema.sql` if attempting the bonus.
- `requirements.txt` with pinned versions.
- `README.md` covering: how to run the notebooks in order, every cleaning decision and its justification, assumptions made, known limitations, and a summary of findings.

**Notebook hygiene:** notebooks must be readable as documents. Markdown cells explaining reasoning, no dead cells, no `df.head()` left over from debugging, no hardcoded absolute paths, sequential execution counts.

# Good Luck!