"""
Data cleaning utilities for the Global Weather Repository dataset.

These functions encode specific findings from manual inspection of the
real CSV (see Phase 1 / Phase 7 Stage 1 discussion), not generic
boilerplate cleaning. Two distinct problems were found and are handled
separately, deliberately:

1. PHYSICALLY IMPOSSIBLE VALUES (temperature, wind, pressure) -- these
   are data errors, not real extreme weather, and are capped/flagged
   based on known physical limits on Earth, not statistical thresholds
   (a naive z-score approach would also flag genuine extreme-but-real
   events like high PM2.5 during wildfire season, which we do NOT want
   to treat the same way as a sensor/parsing error).

2. COUNTRY NAME CONTAMINATION -- the same physical location appears
   under multiple country-name spellings/languages (e.g. "Südkorea" vs
   "South Korea"). Fixed via coordinate clustering: rows within ~1km of
   each other (lat/long rounded to 2 decimals) are assumed to be the
   same place, and the cleanest-looking label among them is chosen as
   canonical. A small manual lookup closes the handful of singleton
   cases coordinate clustering can't resolve alone.
"""

import re

import pandas as pd

# Known physical limits used to flag (not silently drop) impossible readings.
# Sources: highest recorded surface temp ~56.7C (Furnace Creek, CA, 1913);
# highest recorded sustained surface wind speed is well under 500 km/h;
# sea-level-equivalent pressure on Earth has never exceeded ~1085 mb.
# We use generous margins above the real records to avoid flagging genuine,
# merely-unusual weather as an error.
PHYSICAL_LIMITS = {
    "temperature_celsius": (-90.0, 60.0),
    "wind_kph": (0.0, 410.0),
    "pressure_mb": (850.0, 1090.0),
    "humidity": (0.0, 100.0),
}

# Manual canonicalization for the small number of singleton country-name
# entries that coordinate clustering cannot resolve (no ASCII-clean
# variant exists anywhere in the dataset at that location's coordinates).
# Found via inspection -- see notebooks/01_data_cleaning_eda.ipynb.
MANUAL_COUNTRY_TRANSLATION_FIX = {
    "Bélgica": "Belgium",
    "Malásia": "Malaysia",
    "Polônia": "Poland",
    "Turkménistan": "Turkmenistan",
    "Польша": "Poland",
    "كولومبيا": "Colombia",
    "火鸡": "Turkey",
}


def _is_ascii_clean(value: str) -> bool:
    """True if a string looks like a standard English-style country name."""
    return bool(re.fullmatch(r"[A-Za-z\s\.\-']+", value))


def canonicalize_countries(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resolve multilingual/contaminated country labels to a single canonical
    name per physical location, using coordinate clustering.

    Adds a `country_clean` column; does not modify the original `country`
    column, so the raw value remains available for audit.
    """
    df = df.copy()
    df["_lat_r"] = df["latitude"].round(2)
    df["_lon_r"] = df["longitude"].round(2)

    def pick_canonical(group: pd.Series) -> str:
        counts = group.value_counts()
        top_count = counts.iloc[0]
        candidates = counts[counts == top_count].index.tolist()
        ascii_candidates = [c for c in candidates if _is_ascii_clean(c)]
        pool = ascii_candidates if ascii_candidates else candidates
        # Shortest clean candidate tends to be the plain country name
        # rather than a compound/garbled label (e.g. "United States of
        # America" over "USA United States of America").
        return min(pool, key=len)

    canonical_map = df.groupby(["_lat_r", "_lon_r"])["country"].apply(pick_canonical)
    df["country_clean"] = df.set_index(["_lat_r", "_lon_r"]).index.map(canonical_map)
    df["country_clean"] = df["country_clean"].replace(MANUAL_COUNTRY_TRANSLATION_FIX)

    df = df.drop(columns=["_lat_r", "_lon_r"])
    return df


def flag_physical_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds boolean flag columns (`{col}_implausible`) for readings outside
    known physical limits, plus a combined `any_implausible_reading` flag.

    Deliberately does NOT drop or silently clip these rows -- a reviewer
    should be able to see exactly what was flagged and why, and a
    downstream choice (drop vs. clip vs. keep-but-flag) is made explicitly
    in the notebook, not buried in this utility.
    """
    df = df.copy()
    flag_cols = []
    for col, (low, high) in PHYSICAL_LIMITS.items():
        flag_col = f"{col}_implausible"
        df[flag_col] = ~df[col].between(low, high)
        flag_cols.append(flag_col)

    df["any_implausible_reading"] = df[flag_cols].any(axis=1)
    return df


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Full cleaning pipeline: country canonicalization + outlier flagging."""
    df = canonicalize_countries(df)
    df = flag_physical_outliers(df)
    df["last_updated"] = pd.to_datetime(df["last_updated"])
    return df
