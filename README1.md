# CityTransit — Public Transport Ridership Analytics

Four notebooks turn the raw fare-gate export, route master data, vehicle fleet records, and
stops registry into clean aggregate tables ready for Power BI. This document covers how to run
the pipeline, every cleaning decision made along the way and why, the assumptions those
decisions rest on, known limitations worth knowing about before trusting a number, and a
summary of what the data actually shows

## How to run

Requires `pandas`, `numpy`, `matplotlib`, `seaborn`, `pyarrow`, `jupyter`. Run the notebooks
**in order** — each one reads the previous notebook's output, so running out of order (or
running a single cell without the ones before it) will raise `NameError` or produce
silently-wrong results rather than a clean failure.

```
cd notebooks
jupyter notebook
```

1. **`NB1_ingest_and_profile.ipynb`** — loads the four raw CSVs with explicit dtypes, profiles
   every column, flags every data-quality issue. Writes untouched copies to
   `data/interim/*.pkl`.
2. **`NB2_clean.ipynb`** — fixes every issue notebook 01 found. Writes cleaned frames to
   `data/interim/*_clean.pkl` and every dropped row (with a reason) to
   `data/rejects/validations_rejects.csv`.
3. **`NB3_join_and_explore.ipynb`** — joins the cleaned tables into one fact table, asserts the
   join didn't fan out, explores ridership patterns with six charts. Writes
   `data/interim/fact_validations.parquet` (falls back to `.pkl` if `pyarrow` isn't installed).
4. **`NB4_aggregate_and_export.ipynb`** — builds the 10 aggregate tables Power BI consumes.
   Writes each to `data/processed/<name>.csv`, plus `_manifest.csv`.


If a run fails partway, `Kernel → Restart Kernel and Run All Cells` from notebook 01 onward is
the reliable fix — almost every mid-pipeline error encountered during development traced back
to running cells out of order rather than an actual bug.



-----------------------------------------------------

## Cleaning decisions and justification (notebook 02)

Every rule below is its own function in the notebook, applied immediately after definition, with
every dropped row logged to a running counter (`drop_log`) and written to the rejects file with a
`reject_reason`.

### Validations

| Decision | Why |
|---|---|
| Drop exact duplicate rows, then duplicate `validation_id` | Notebook 01 found ~1% exact duplicates (gate double-reads) and separately-conflicting duplicate IDs — two different problems, tracked separately. |
| Parse `validation_ts` via three explicit formats (ISO, `DD/MM/YYYY HH:MM`, spelled-out text), not one blanket `pd.to_datetime` | The three formats found in profiling would silently misparse or fail under a single auto-inferred parse (e.g. day/month ambiguity). Each subset is matched to its known pattern first. |
| Strip whitespace from every ID column | `route_id` carried whitespace on ~15% of raw rows (~12,000) — systemic, not a handful of typos. Has to be fixed before any join. |
| Map `fare_type`'s ~17 raw labels to 5 canonical categories (`Adult`, `Student`, `Senior`, `Child`, `Pass Holder`) by hand | Not a casing fix — labels like `Full Fare` and `Adult` are different *words* for the same category. Collapsing them is a judgment call, made explicit via a lookup table rather than fuzzy-matched. |
| Map `transfer_flag`'s 6 encodings (`Y`/`N`, `0`/`1`, `TRUE`/`FALSE`) to a real nullable boolean | `.astype(bool)` on raw strings would treat `"FALSE"` as truthy (non-empty string). Explicit mapping avoids that. |
| Drop null `passenger_count`; keep negative values as-is, flagged with a new `is_reversed` column | Negative counts are read as reversed/refunded transactions, not corrupted data — kept rather than sign-flipped, so `revenue` can net them out honestly. This is a judgment call, not a certainty (see Limitations). |
| Impute null `fare_amount` with the median **for that `fare_type`**; cap values above the 99.5th percentile at that percentile | Fares vary hugely by category (Pass Holder medians $0.00, Adult $2.50) — a global median would misrepresent every category. Capping (not dropping) the round sentinel values (`9999`, `5000`, `2000`, `1234.56`) preserves ridership counts while preventing them from distorting revenue sums. |
| Fill blank `card_id` with `SINGLE_RIDE` | ~12% missing `card_id` reads as cash/no-card payment, not a data gap — an explicit sentinel beats leaving it null or dropping the row. |

### Routes, Vehicles, Stops

| Decision | Why |
|---|---|
| Title-case `route_name`/`stop_name`, Title-case + strip `mode` | Inconsistent casing and stray whitespace found in profiling (e.g. `"bus"`, `"BUS "`, `"Bus"` all meaning the same thing). |
| Fill null `district` with `"Unknown"` | Small number of nulls (3), not worth dropping rows over; explicit label beats a silent blank. |
| Fill null `route_length_km` with the median **for that mode** | Bus, Tram, and Metro routes have structurally different typical lengths — a global median would be wrong for all three. |
| Set `year_manufactured` outside `[1980, 2026]` to null | Values of `1899` and `2035` are impossible (predates motor vehicles / postdates the dataset) — read as sentinel/placeholder errors, nulled rather than guessed at. |
| Derive `vehicle_age_band` against the **latest year present in the validations data**, not today's real-world date | Treats the dataset as a snapshot as-of its own activity — re-running this pipeline next year on the same historical export shouldn't shift every vehicle into an older band. |
| Fill null `capacity` with the median **for that `vehicle_type`** | A Standard Bus and a Metro Set aren't comparable — same reasoning as `route_length_km`. |
| Map `has_shelter`'s 4 encodings to a real boolean | Same reasoning and same mapping function as `transfer_flag`. |

### Referential integrity

Validations whose `route_id`, `vehicle_id`, or `stop_id` doesn't exist in the corresponding
master table (after whitespace stripping) are dropped and logged — a handful of genuine orphans
(~14 per ID column), not a formatting artifact. `card_id = 'SINGLE_RIDE'` plays no part in this
check — a row is dropped here only for a genuinely bad reference, never for its payment method.

### Result

Of 81,600 raw validation rows, **2,451 (~3%) were dropped**: exact duplicates (802), duplicate
`validation_id` (798), null `passenger_count` (811), orphan foreign keys (~41 across all three ID
columns). **79,149 rows survive into the fact table.**

----------------------------------------------------------


## Join decisions (notebook 03)

All three joins (`validations → routes`, `→ vehicles`, `→ stops`) are `LEFT JOIN`s, with
`validations` as the base table. On this data an `INNER JOIN` would produce identical results
(notebook 02 already guarantees every ID matches), but the two fail differently if that
guarantee is ever violated: `INNER JOIN` would silently drop rows with no error; `LEFT JOIN`
surfaces visible nulls instead. The row count is asserted equal to the cleaned validations count
immediately after joining, specifically to catch a fan-out from an unexpected duplicate ID in a
master table — verified both to pass on clean data and to correctly fail (with a clear message)
when a duplicate route ID was deliberately injected during testing.

`district` exists in both `routes` and `stops` (a route's district isn't always the same as a
stop's physical district) — renamed to `route_district`/`stop_district` before joining so
neither silently overwrites the other.

---

## Assumptions

These are judgment calls baked into the numbers — stated explicitly so they can be revisited if
they turn out to be wrong:

- **`total_boardings` = `sum(passenger_count)`, not row count.** Nets out reversed/refunded
  transactions (negative `passenger_count`), consistent with how `revenue` is calculated.
- **`unique_cards` excludes the `SINGLE_RIDE` sentinel entirely** — it represents many different
  anonymous cash/no-card riders collapsed into one shared value, not one repeat customer.
- **Negative `passenger_count` = a reversed/refunded transaction**, kept as a signed value rather
  than corrected to positive. This is the more conservative of two readings, not a certainty.
- **A "vehicle-trip" is approximated as one vehicle, on one route, within one hour** — there's no
  explicit trip ID in the source data. `load_factor` and everything derived from it (route,
  vehicle, and peak-period average load factors) inherits this approximation.
- **`vehicle_age_band`'s reference year is the latest year present in the data**, not the
  real-world current date.
- **`day_of_week` and `is_weekend` are built from `dt.dayofweek`** (a locale-independent integer),
  not `dt.day_name()` — the latter returns localized strings on non-English-locale machines,
  which silently broke `is_weekend` during development (every row read as weekday) before this
  fix.

---

## Known limitations

- **Vehicle-hour load factor never exceeds ~10% of capacity anywhere in the data**, and the
  network-wide average is ~0.96%. This reads as a data-granularity artifact — validations are
  sparse relative to the vehicle-hour grouping (roughly one tap per vehicle per hour on average
  across 180 vehicles and six months) — rather than genuine spare capacity. Any capacity-planning
  decision built on this number should be validated against fare-gate hardware logs or a manual
  occupancy count first.
- **`unique_cards` is a floor, not a true unique-rider count.** Every `SINGLE_RIDE` payment is
  excluded rather than counted, so the true number of distinct people who rode the network is
  higher than 23,460 — by an unknown amount, since anonymous single-ride payments carry no
  identifier at all.
- **The negative-`passenger_count`-as-reversal reading is unverified.** It's the more
  information-preserving of two plausible interpretations (the other being a sign-flip data
  bug), but nothing in the data confirms which is correct.
- **`pyarrow` was not available in the environment this pipeline was developed in**, so
  `fact_validations.parquet` falls back to `.pkl` with a printed warning. The parquet code path
  is correct and spec-compliant but was only tested via its fallback — confirm it produces a real
  `.parquet` file in an environment with `pyarrow` installed.
- **East Depot's newer (0-5 year) vehicles show the lowest utilisation** in the fleet — but this
  sits inside the same load-factor granularity limitation above, so it's a lead worth
  investigating specifically (e.g. via manual occupancy checks on those vehicle IDs), not a
  confirmed operational finding on its own.

---

## Summary of findings

**Network scale (Jan–Jun 2024):** 85,247 total boardings, 156,511.75 in revenue, 23,460 unique
registered cards (plus an unknown further number of single-ride/cash riders), average vehicle-
hour load factor of 0.96% (see limitation above on interpreting this number).

**Ridership is stable, not growing or shrinking.** Month-over-month change alternates between
roughly +5–7% and -4–8% with no directional trend — consistent with a mature, saturated network
rather than one still gaining riders.

**Bus carries the majority of ridership** (~57%), with Tram (~34%) and Metro (~10%) trailing,
roughly proportional to each mode's route count.

**Demand is sharply peaked and consistent across modes.** AM Peak (07-09h) and PM Peak (16-18h)
together account for the majority of daily boardings for Bus, Tram, and Metro alike — none of
the three modes shows a materially different demand curve, and weekday/weekend hourly shapes are
similar (weekend volume is consistently lower throughout the day, not shifted to different hours).

**Fare mix is essentially flat month to month:** Adult ~55%, Student ~15%, Senior ~12%,
Pass Holder ~10%, Child ~8%, varying by at most ~1 percentage point across the six months.
Pass Holder fares are worth flagging specifically: ~10% of boardings but negligible recorded
revenue, since pass-based trips aren't charged per ride.

**No single route dominates demand.** The top 15 routes are tightly bunched (1,400–1,506
boardings each over six months), but per-km efficiency (`boardings_per_km`) varies widely across
the network (9.6 to 68.7) — worth using efficiency, not raw volume, to judge which routes are
genuinely over- or under-served.

**Vehicle utilisation is lowest at East Depot and among the newest (0–5 year) vehicles**, and
highest at North Depot and among 11–20 year vehicles — the opposite of what age alone would
predict. This is a lead for investigation (see Limitations), not a settled conclusion.

**Transfer rates are similar across all three modes** (35–39%), with a gentle upward drift from
January to June — behaviour that reads as a rider habit rather than a mode-specific pattern.

### Recommendations for the agency

1. Before any capacity-expansion or fleet-reallocation decision, validate the load-factor metric
   against fare-gate hardware or a manual occupancy count — the current figure is more likely a
   data-granularity artifact than a true measure of spare capacity.
2. Peak-hour service levels matter far more than off-peak for planning purposes, and since peak
   timing lines up closely across all three modes, schedule changes should be evaluated
   network-wide rather than one mode at a time.
3. Investigate East Depot's newer vehicles specifically (not the fleet broadly) for the
   underutilisation pattern before reallocating any vehicles based on it.
4. Use `boardings_per_km`, not raw ridership, when judging route performance — the top-15
   leaderboard alone doesn't distinguish an efficient short route from an inefficient long one.
