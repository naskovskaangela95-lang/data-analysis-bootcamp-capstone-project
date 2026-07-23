#!/usr/bin/env python3
"""
CityTransit capstone — synthetic data generator (INSTRUCTOR ONLY).

Produces the four raw CSVs described in README.md:

    data/raw/validations.csv   (~80,000 rows)
    data/raw/routes.csv        (~60 rows)
    data/raw/vehicles.csv      (~180 rows)
    data/raw/stops.csv         (~400 rows)

Everything is driven by a single SEED so every student gets identical data.
Regenerate on demand with:  python generate_data.py

The generator deliberately injects the data-quality problems listed in the
"Data Generation Notes" section of the README so the cleaning notebooks have
real work to do. Each injection is tagged with an `# INJECT:` comment.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SEED = 42  # Documented seed — change only if you intend to reshuffle everyone.

N_VALIDATIONS = 80_000
N_ROUTES = 60
N_VEHICLES = 180
N_STOPS = 400

# Ridership window. A ~6-month span gives the monthly aggregations something
# to chew on without ballooning the file.
DATE_START = dt.date(2024, 1, 1)
DATE_END = dt.date(2024, 6, 30)

DISTRICTS = [
    "Centro", "Northgate", "Riverside", "Old Town", "Harbourside",
    "Westend", "Eastfield", "Hillcrest", "Southbank", "Parkview",
]
ZONES = ["Zone 1", "Zone 2", "Zone 3"]
DEPOTS = ["Central Depot", "North Depot", "East Depot", "Riverside Depot"]

# fare_type raw variants -> the value's canonical form is whatever the students
# normalise it to. We emit messy casing / synonyms on purpose. INJECT: casing.
FARE_TYPE_VARIANTS = {
    "Adult":       ["Adult", "adult", "ADULT", "Full Fare"],
    "Student":     ["Student", "student", "STUDENT"],
    "Senior":      ["Senior", "senior", "Senior Citizen"],
    "Child":       ["Child", "child", "Kid"],
    "Pass Holder": ["Pass Holder", "pass holder", "PassHolder", "Monthly Pass"],
}
FARE_TYPE_WEIGHTS = [0.55, 0.15, 0.12, 0.08, 0.10]  # Adult..Pass Holder

# Base fare per canonical fare_type (Pass Holder rides are effectively prepaid).
FARE_BASE = {
    "Adult": 2.50, "Student": 1.50, "Senior": 1.20, "Child": 1.00, "Pass Holder": 0.0,
}

# transfer_flag: six spellings mixed together.  INJECT: mixed booleans.
TRANSFER_FLAG_VARIANTS = ["Y", "N", "1", "0", "TRUE", "FALSE"]

VEHICLE_TYPES = ["Standard Bus", "Articulated Bus", "Tram", "Metro Set"]
VEHICLE_CAPACITY = {  # nominal capacity per type; jittered per vehicle
    "Standard Bus": 70, "Articulated Bus": 120, "Tram": 200, "Metro Set": 600,
}
# Map a vehicle_type to the route mode it can serve, so joins are coherent.
TYPE_TO_MODE = {
    "Standard Bus": "Bus", "Articulated Bus": "Bus", "Tram": "Tram", "Metro Set": "Metro",
}

MODE_CANONICAL = ["Bus", "Tram", "Metro"]
MODE_WEIGHTS = [0.65, 0.20, 0.15]
# mode raw variants -> messy casing incl. trailing space.  INJECT: casing.
MODE_VARIANTS = {
    "Bus": ["Bus", "bus", "BUS ", "BUS"],
    "Tram": ["Tram", "tram", "TRAM "],
    "Metro": ["Metro", "metro", "METRO "],
}


# --------------------------------------------------------------------------- #
# Master tables
# --------------------------------------------------------------------------- #
def make_routes(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    rows = []
    modes = rng.choice(MODE_CANONICAL, size=N_ROUTES, p=MODE_WEIGHTS)
    for i, mode in enumerate(modes, start=1):
        route_id = f"R{i:03d}"
        # route_name with leading/trailing whitespace.  INJECT: whitespace.
        name = f"{fake.street_name()} Line"
        name = f"  {name}  " if rng.random() < 0.4 else name
        # mode with messy casing.  INJECT: casing / trailing space.
        mode_raw = rng.choice(MODE_VARIANTS[mode])

        district = rng.choice(DISTRICTS)
        district = None if rng.random() < 0.08 else district  # INJECT: null district (~8%)

        length = round(float(rng.uniform(3, 25)), 1)
        length = None if rng.random() < 0.10 else length      # INJECT: null length (~10%)

        trips = int(rng.integers(20, 220))
        rows.append({
            "route_id": route_id,
            "route_name": name,
            "mode": mode_raw,
            "district": district,
            "route_length_km": length,
            "scheduled_trips_per_day": trips,
        })
    df = pd.DataFrame(rows)
    # keep a clean mode alongside for internal FK coherence (dropped before save)
    df["_mode_clean"] = modes
    return df


def make_vehicles(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    rows = []
    # Roughly match the mode mix so most validations find a same-mode vehicle.
    types = rng.choice(VEHICLE_TYPES, size=N_VEHICLES, p=[0.45, 0.20, 0.20, 0.15])
    impossible_idx = set(rng.choice(N_VEHICLES, size=15, replace=False))  # INJECT: bad years
    for i, vtype in enumerate(types):
        vehicle_id = f"V{i + 1:04d}"
        cap = int(round(VEHICLE_CAPACITY[vtype] * rng.uniform(0.85, 1.15)))
        cap = None if rng.random() < 0.06 else cap  # INJECT: null capacity (~6%)

        if i in impossible_idx:
            year = int(rng.choice([1899, 2035]))     # INJECT: impossible year (~15 vehicles)
        else:
            year = int(rng.integers(1985, 2025))

        rows.append({
            "vehicle_id": vehicle_id,
            "vehicle_type": vtype,
            "capacity": cap,
            "year_manufactured": year,
            "depot": rng.choice(DEPOTS),
        })
    df = pd.DataFrame(rows)
    df["_mode_clean"] = [TYPE_TO_MODE[t] for t in types]
    return df


def make_stops(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    rows = []
    for i in range(1, N_STOPS + 1):
        stop_id = f"S{i:04d}"
        base = f"{fake.street_name()} Stop"
        # stop_name whitespace + casing issues.  INJECT: whitespace/casing.
        r = rng.random()
        if r < 0.25:
            name = f"  {base}  "
        elif r < 0.45:
            name = base.upper()
        elif r < 0.60:
            name = base.lower()
        else:
            name = base
        # has_shelter as Y/N/1/0 mixed.  INJECT: mixed booleans.
        shelter = rng.choice(["Y", "N", "1", "0"])
        rows.append({
            "stop_id": stop_id,
            "stop_name": name,
            "district": rng.choice(DISTRICTS),
            "zone": rng.choice(ZONES, p=[0.5, 0.3, 0.2]),
            "has_shelter": shelter,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Timestamps — bimodal hourly distribution + three string formats
# --------------------------------------------------------------------------- #
def hour_weights() -> np.ndarray:
    """Bimodal daily curve with AM (~08:00) and PM (~17:30) peaks."""
    hours = np.arange(24)
    am = np.exp(-0.5 * ((hours - 8) / 1.1) ** 2)
    pm = np.exp(-0.5 * ((hours - 17.5) / 1.3) ** 2)
    midday = 0.35 * np.exp(-0.5 * ((hours - 12.5) / 3.0) ** 2)
    base = 0.02  # keep a thin overnight tail
    w = 1.0 * am + 1.1 * pm + midday + base
    return w / w.sum()


def format_timestamp(ts: dt.datetime, fmt_choice: str) -> str:
    """Render a datetime in one of three formats (70/20/10 mix)."""
    if fmt_choice == "iso":
        return ts.strftime("%Y-%m-%d %H:%M:%S")            # 2024-03-15 07:42:11
    if fmt_choice == "eu":
        return ts.strftime("%d/%m/%Y %H:%M")               # 15/03/2024 07:42
    # "long": March 15, 2024 7:42 AM  (build 12h hour without leading zero, cross-platform)
    hour12 = ts.hour % 12 or 12
    ampm = "AM" if ts.hour < 12 else "PM"
    return f"{ts.strftime('%B')} {ts.day}, {ts.year} {hour12}:{ts.strftime('%M')} {ampm}"


# --------------------------------------------------------------------------- #
# Fact table: validations
# --------------------------------------------------------------------------- #
def make_validations(
    rng: np.random.Generator,
    routes: pd.DataFrame,
    vehicles: pd.DataFrame,
    stops: pd.DataFrame,
) -> pd.DataFrame:
    n = N_VALIDATIONS
    hw = hour_weights()
    n_days = (DATE_END - DATE_START).days + 1

    # --- pick a coherent (route, vehicle) by mode where possible -------------
    route_ids = routes["route_id"].to_numpy()
    route_modes = routes["_mode_clean"].to_numpy()
    veh_by_mode = {
        m: vehicles.loc[vehicles["_mode_clean"] == m, "vehicle_id"].to_numpy()
        for m in MODE_CANONICAL
    }
    all_veh = vehicles["vehicle_id"].to_numpy()
    stop_ids = stops["stop_id"].to_numpy()

    ridx = rng.integers(0, len(route_ids), size=n)
    chosen_routes = route_ids[ridx]
    chosen_modes = route_modes[ridx]

    chosen_vehicles = np.empty(n, dtype=object)
    for m in MODE_CANONICAL:
        mask = chosen_modes == m
        pool = veh_by_mode[m] if len(veh_by_mode[m]) else all_veh
        chosen_vehicles[mask] = rng.choice(pool, size=int(mask.sum()))

    chosen_stops = rng.choice(stop_ids, size=n)

    # --- timestamps ----------------------------------------------------------
    day_offsets = rng.integers(0, n_days, size=n)
    # weekends carry lighter, flatter demand
    dates = [DATE_START + dt.timedelta(days=int(o)) for o in day_offsets]
    hours = rng.choice(24, size=n, p=hw)                    # bimodal AM/PM peaks
    minutes = rng.integers(0, 60, size=n)
    seconds = rng.integers(0, 60, size=n)
    timestamps = [
        dt.datetime(d.year, d.month, d.day, int(h), int(mi), int(s))
        for d, h, mi, s in zip(dates, hours, minutes, seconds)
    ]
    # three formats mixed ~70/20/10.  INJECT: mixed timestamp formats.
    fmt_choice = rng.choice(["iso", "eu", "long"], size=n, p=[0.70, 0.20, 0.10])
    ts_str = [format_timestamp(t, f) for t, f in zip(timestamps, fmt_choice)]

    # --- fare_type (with messy variants) ------------------------------------
    canon_fare = rng.choice(list(FARE_TYPE_VARIANTS.keys()), size=n, p=FARE_TYPE_WEIGHTS)
    fare_type_raw = np.array(
        [rng.choice(FARE_TYPE_VARIANTS[c]) for c in canon_fare], dtype=object
    )

    # --- fare_amount ---------------------------------------------------------
    fare_amount = np.array(
        [max(0.0, round(FARE_BASE[c] + rng.normal(0, 0.15), 2)) for c in canon_fare],
        dtype=float,
    )
    # ~1.5% nulls.  INJECT: null fare_amount.
    null_fare = rng.random(n) < 0.015
    fare_amount[null_fare] = np.nan
    # ~25 absurd outliers above 1,000.  INJECT: fare outliers.
    outlier_idx = rng.choice(np.where(~null_fare)[0], size=25, replace=False)
    fare_amount[outlier_idx] = rng.choice([9999.0, 5000.0, 1234.56, 2000.0], size=25)

    # --- passenger_count -----------------------------------------------------
    passenger_count = np.ones(n, dtype=float)
    # a minority carry 2-3 (e.g. group taps on the same card)
    multi = rng.random(n) < 0.06
    passenger_count[multi] = rng.integers(2, 4, size=int(multi.sum()))
    # a few negatives = failed/reversed validations.  INJECT: negatives.
    neg = rng.random(n) < 0.004
    passenger_count[neg] = rng.integers(-3, 0, size=int(neg.sum()))
    # ~1% nulls.  INJECT: null passenger_count.
    null_pax = rng.random(n) < 0.01
    passenger_count[null_pax] = np.nan

    # --- card_id -------------------------------------------------------------
    card_id = np.array([f"CARD-{rng.integers(1, 25000):06d}" for _ in range(n)], dtype=object)
    blank_card = rng.random(n) < 0.12                       # INJECT: ~12% blank card_id
    card_id[blank_card] = ""

    # --- transfer_flag (six spellings) --------------------------------------
    transfer_flag = rng.choice(TRANSFER_FLAG_VARIANTS, size=n, p=[0.30, 0.45, 0.05, 0.10, 0.03, 0.07])

    # --- route_id trailing whitespace on some rows.  INJECT: whitespace ------
    route_out = chosen_routes.astype(object).copy()
    ws_mask = rng.random(n) < 0.15
    route_out[ws_mask] = np.array([f"{r} " for r in route_out[ws_mask]], dtype=object)

    # --- validation_id -------------------------------------------------------
    validation_id = np.array([f"VAL-{i:07d}" for i in range(1, n + 1)], dtype=object)

    df = pd.DataFrame({
        "validation_id": validation_id,
        "validation_ts": ts_str,
        "route_id": route_out,
        "vehicle_id": chosen_vehicles,
        "stop_id": chosen_stops,
        "card_id": card_id,
        "fare_type": fare_type_raw,
        "fare_amount": fare_amount,
        "passenger_count": passenger_count,
        "transfer_flag": transfer_flag,
    })

    # --- ~40 broken foreign keys.  INJECT: dangling FKs ----------------------
    bad_idx = rng.choice(n, size=40, replace=False)
    b1, b2, b3 = np.array_split(bad_idx, 3)
    df.loc[b1, "route_id"] = "R999"
    df.loc[b2, "vehicle_id"] = "V9999"
    df.loc[b3, "stop_id"] = "S9999"

    # --- ~2% duplicate validation_id rows.  INJECT: duplicates ---------------
    n_dup = int(0.02 * n)
    dup_src = rng.choice(n, size=n_dup, replace=False)
    dups = df.iloc[dup_src].copy()
    # Half are exact-row duplicates; half reuse the id but differ elsewhere,
    # so students must handle both "drop exact dup" and "dup id keep first".
    half = n_dup // 2
    jitter = dups.iloc[half:].copy()
    jitter["stop_id"] = rng.choice(stop_ids, size=len(jitter))
    dups = pd.concat([dups.iloc[:half], jitter], ignore_index=True)

    df = pd.concat([df, dups], ignore_index=True)
    # shuffle so duplicates and bad rows aren't clustered at the end
    df = df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    return df


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CityTransit capstone raw CSVs.")
    parser.add_argument(
        "--out", default=None,
        help="Output directory for raw CSVs (default: <repo>/data/raw).",
    )
    parser.add_argument("--seed", type=int, default=SEED, help=f"Random seed (default {SEED}).")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else Path(__file__).resolve().parent.parent / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    print(f"Seed = {args.seed}")
    print("Generating master tables...")
    routes = make_routes(rng, fake)
    vehicles = make_vehicles(rng, fake)
    stops = make_stops(rng, fake)

    print("Generating validations (this is the big one)...")
    validations = make_validations(rng, routes, vehicles, stops)

    # drop internal helper columns before writing
    routes_out = routes.drop(columns=["_mode_clean"])
    vehicles_out = vehicles.drop(columns=["_mode_clean"])

    # Use nullable integer dtype so int columns with injected nulls write as
    # "70"/"" rather than "70.0"/"" — keeps IDs-and-counts looking like ints.
    vehicles_out["capacity"] = vehicles_out["capacity"].astype("Int64")
    validations["passenger_count"] = validations["passenger_count"].astype("Int64")

    files = {
        "routes.csv": routes_out,
        "vehicles.csv": vehicles_out,
        "stops.csv": stops,
        "validations.csv": validations,
    }
    for name, df in files.items():
        path = out_dir / name
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"  wrote {path}  ({len(df):,} rows, {df.shape[1]} cols)")

    print("\nDone. Quick sanity check on injected issues:")
    v = validations
    print(f"  duplicate validation_id rows : {v['validation_id'].duplicated().sum():,}")
    print(f"  blank card_id                : {(v['card_id'] == '').mean():.1%}")
    print(f"  null fare_amount             : {v['fare_amount'].isna().mean():.1%}")
    print(f"  null passenger_count         : {v['passenger_count'].isna().mean():.1%}")
    print(f"  fare outliers (>1000)        : {(v['fare_amount'] > 1000).sum()}")
    print(f"  negative passenger_count     : {(v['passenger_count'] < 0).sum()}")
    print(f"  distinct transfer_flag       : {sorted(v['transfer_flag'].unique().tolist())}")
    print(f"  dangling route_id (R999)     : {(v['route_id'].str.strip() == 'R999').sum()}")
    print(f"  distinct raw fare_type       : {sorted(v['fare_type'].unique().tolist())}")
    print(f"  bad vehicle years (1899/2035): {vehicles_out['year_manufactured'].isin([1899, 2035]).sum()}")


if __name__ == "__main__":
    main()
