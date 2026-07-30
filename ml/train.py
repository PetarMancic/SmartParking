"""
Faza 2 - Model za predikciju (XGBoost regresija).

Trenira model koji predvidja OccupancyRate na osnovu vremena i parkinga,
evaluira ga (RMSE, MAE) naspram baseline-a (prosek) i cuva u ml/model.joblib.
"""

import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "parking.csv")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.joblib")

FEATURE_COLUMNS = ["Hour", "Minute", "DayOfWeekNum", "ParkEncoded", "Capacity"]
TARGET_COLUMN = "OccupancyRate"


def load_and_prepare_data() -> tuple[pd.DataFrame, LabelEncoder]:
    df = pd.read_csv(DATA_PATH)
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"])
    df = df.sort_values("LastUpdated").reset_index(drop=True)

    df["Hour"] = df["LastUpdated"].dt.hour
    df["Minute"] = df["LastUpdated"].dt.minute
    df["DayOfWeekNum"] = df["LastUpdated"].dt.dayofweek

    park_encoder = LabelEncoder()
    df["ParkEncoded"] = park_encoder.fit_transform(df["SystemCodeNumber"])

    return df, park_encoder


def chronological_split(df: pd.DataFrame, test_fraction: float = 0.2):
    split_index = int(len(df) * (1 - test_fraction))
    train_df = df.iloc[:split_index]
    test_df = df.iloc[split_index:]
    return train_df, test_df


def evaluate(y_true, y_pred, label: str) -> None:
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    print(f"{label}: RMSE = {rmse:.3f}, MAE = {mae:.3f}")


def main() -> None:
    df, park_encoder = load_and_prepare_data()
    train_df, test_df = chronological_split(df)

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df[TARGET_COLUMN]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[TARGET_COLUMN]

    print(f"Train: {len(train_df)} redova, Test: {len(test_df)} redova")
    print()

    # Baseline: uvek predvidja prosecnu popunjenost iz trening skupa
    baseline_pred = np.full(len(y_test), y_train.mean())
    evaluate(y_test, baseline_pred, "Baseline (prosek)")

    model = XGBRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(X_train, y_train)

    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)

    evaluate(y_train, train_pred, "XGBoost (train)")
    evaluate(y_test, test_pred, "XGBoost (test)")

    joblib.dump({"model": model, "park_encoder": park_encoder, "features": FEATURE_COLUMNS}, MODEL_PATH)
    print()
    print(f"Model sacuvan: {MODEL_PATH}")


if __name__ == "__main__":
    main()
