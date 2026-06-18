"""
Forecasting models for temperature, trained on the Global Weather
Repository dataset. Uses `last_updated` as the time index (D9).

Two models, evaluated against each other (D12):
1. Seasonal-naive baseline -- predicts each day's temperature as the
   historical mean temperature for that (location, day-of-year). This
   is the bar every real model must beat to be worth using.
2. Gradient boosting regressor -- uses calendar features (day-of-year
   as sin/cos to capture seasonality) plus location features (lat,
   long) to predict temperature for any location, not just the 268
   in the training set.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day_of_year"] = df["last_updated"].dt.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)
    return df


def seasonal_naive_predict(train_df: pd.DataFrame, test_df: pd.DataFrame) -> np.ndarray:
    """Baseline: mean temp for this (location, day-of-year) in training data,
    falling back to the location's overall mean if that exact day-of-year
    wasn't observed for this location in training."""
    train_df = add_time_features(train_df)
    test_df = add_time_features(test_df)

    by_loc_doy = train_df.groupby(["location_name", "day_of_year"])["temperature_celsius"].mean()
    by_loc = train_df.groupby("location_name")["temperature_celsius"].mean()
    global_mean = train_df["temperature_celsius"].mean()

    preds = []
    for _, row in test_df.iterrows():
        key = (row["location_name"], row["day_of_year"])
        if key in by_loc_doy.index:
            preds.append(by_loc_doy[key])
        elif row["location_name"] in by_loc.index:
            preds.append(by_loc[row["location_name"]])
        else:
            preds.append(global_mean)
    return np.array(preds)


def train_gradient_boosting(train_df: pd.DataFrame) -> tuple[GradientBoostingRegressor, list[str]]:
    """Trains a global model using calendar + location features. Returns
    the fitted model and the exact feature column order it expects."""
    train_df = add_time_features(train_df)
    train_df = train_df[~train_df["any_implausible_reading"]]

    features = ["latitude", "longitude", "doy_sin", "doy_cos"]
    X = train_df[features]
    y = train_df["temperature_celsius"]

    model = GradientBoostingRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        random_state=42,
    )
    model.fit(X, y)
    return model, features


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": mean_squared_error(y_true, y_pred) ** 0.5,
    }
