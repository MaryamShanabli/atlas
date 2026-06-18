"""
Anomaly detection for the Atlas platform.

Two distinct notions of "anomalous", deliberately kept separate:

1. Physically implausible -- a reading violates a hard physical limit
   (see data_cleaning.PHYSICAL_LIMITS). Always an error, never "real".
2. Statistically unusual -- a reading is far from this specific
   location's own historical distribution, but is itself physically
   plausible (e.g. unusually high PM2.5 during a smoke event). This is
   real signal, not an error, and is what /anomaly-check reports to
   users in the live API.
"""

import pandas as pd


def build_location_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-location mean/std for the fields users actually care about,
    used as the historical baseline for statistical anomaly checks.
    Only computed on physically plausible rows.
    """
    plausible = df[~df["any_implausible_reading"]]
    baseline = plausible.groupby(["location_name", "country_clean"]).agg(
        temp_mean=("temperature_celsius", "mean"),
        temp_std=("temperature_celsius", "std"),
        pm25_mean=("air_quality_PM2.5", "mean"),
        pm25_std=("air_quality_PM2.5", "std"),
        n_observations=("temperature_celsius", "count"),
    ).reset_index()
    return baseline


def check_anomaly(reading: dict, baseline_row: pd.Series, z_threshold: float = 2.5) -> dict:
    """
    Compare a single live reading against a location's historical baseline.

    Returns a verdict dict matching the weather_queries.is_anomalous /
    anomaly_reason schema from Phase 4. z_threshold=2.5 is a deliberate
    choice: ~2.5 standard deviations flags roughly the most extreme 1%
    of readings under a normal approximation, which is a reasonable
    "genuinely unusual" bar without flagging routine day-to-day swings.
    """
    reasons = []

    temp = reading.get("temperature_celsius")
    if temp is not None and baseline_row["temp_std"] and baseline_row["temp_std"] > 0:
        z = abs(temp - baseline_row["temp_mean"]) / baseline_row["temp_std"]
        if z > z_threshold:
            direction = "higher" if temp > baseline_row["temp_mean"] else "lower"
            reasons.append(
                f"Temperature is {direction} than usual for this location "
                f"({temp}°C vs typical {baseline_row['temp_mean']:.1f}°C)"
            )

    pm25 = reading.get("air_quality_PM2.5")
    if pm25 is not None and baseline_row["pm25_std"] and baseline_row["pm25_std"] > 0:
        z = abs(pm25 - baseline_row["pm25_mean"]) / baseline_row["pm25_std"]
        if z > z_threshold:
            reasons.append(
                f"Air quality (PM2.5) is unusually elevated for this location "
                f"({pm25:.1f} vs typical {baseline_row['pm25_mean']:.1f})"
            )

    return {
        "is_anomalous": len(reasons) > 0,
        "anomaly_reason": "; ".join(reasons) if reasons else None,
    }
