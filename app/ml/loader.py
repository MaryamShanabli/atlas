"""
ML artifact loader. Loaded once at application startup.
Exposes two functions the service layer calls:
  - predict_temperature(lat, lon, date) -> float
  - get_location_baseline(location_name, country_clean) -> dict | None
"""
import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_MODELS_DIR = Path(__file__).parent.parent.parent / "models"

_forecast_bundle = joblib.load(_MODELS_DIR / "forecast_model.joblib")
_model = _forecast_bundle["model"]
_features = _forecast_bundle["features"]

_baselines: pd.DataFrame = joblib.load(_MODELS_DIR / "location_baselines.joblib")
_known_coords: pd.DataFrame = joblib.load(_MODELS_DIR / "known_coverage_coords.joblib")


def predict_temperature(lat: float, lon: float, target_date: datetime.date) -> float:
    """Predict temperature for any lat/lon on a given date using the trained model."""
    doy = target_date.timetuple().tm_yday
    X = pd.DataFrame([{
        "latitude": lat,
        "longitude": lon,
        "doy_sin": np.sin(2 * np.pi * doy / 365.25),
        "doy_cos": np.cos(2 * np.pi * doy / 365.25),
    }])[_features]
    return float(_model.predict(X)[0])


def has_model_coverage(lat: float, lon: float, radius_km: float = 50.0) -> bool:
    """
    True if this location is within radius_km of any location the model
    was trained on. Uses a simple equirectangular approximation (fine at
    this radius) rather than exact coordinate matching, since a geocoder's
    resolved point for a city and the dataset's recorded point for the
    same city are rarely bit-for-bit identical -- they're the same place,
    just slightly different representative coordinates.
    """
    if _known_coords.empty:
        return False
    lat_rad = np.radians(lat)
    dlat = np.radians(_known_coords["latitude"] - lat)
    dlon = np.radians(_known_coords["longitude"] - lon)
    # Equirectangular approximation: good enough at <100km, much cheaper than haversine.
    x = dlon * np.cos(lat_rad)
    y = dlat
    dist_km = np.sqrt(x**2 + y**2) * 6371.0
    return bool((dist_km <= radius_km).any())


def get_location_baseline(location_name: str, country_clean: str) -> dict | None:
    """Return historical mean/std for a location, or None if not in training data."""
    row = _baselines[
        (_baselines["location_name"] == location_name) &
        (_baselines["country_clean"] == country_clean)
    ]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "temp_mean": r["temp_mean"],
        "temp_std": r["temp_std"],
        "pm25_mean": r["pm25_mean"],
        "pm25_std": r["pm25_std"],
        "n_observations": int(r["n_observations"]),
    }
