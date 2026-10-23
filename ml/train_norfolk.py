"""
Faza 1 (master rad, redizajnirano 2026-10-17) - trening JEDNOG XGBoost modela
za Norfolk koji ume da predvidi zauzetost za BILO KOJI horizont na 30-min
mrezi (od 30 min do MAX_HORIZON_STEPS*30 min unapred), ne samo za tri fiksna
horizonta.

Razlog izmene: profesor nije trazio bas tri fiksna horizonta (30min/1h/2h) -
to je bila odluka iz ranijeg referentnog eksperimenta koja se uvukla u plan.
Profesorov stvaran zahtev ("predvidjena zauzetost ... sta god je moguce") je
otvoren, pa "horizont" sad postaje obicna ulazna promenljiva
(`horizon_minutes`) umesto da se trenira poseban model po horizontu - vidi
ml/data_prep.py (HORIZON_STEPS_RANGE, prepare_multi_horizon_dataset) i
PROGRESS.md.

Cuva jedan model (ml/model_norfolk.joblib) i metrike (MAE/RMSE po horizontu,
MAE po parkingu x horizontu).

Pokretanje:
    python ml/train_norfolk.py
"""

import os

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from data_prep import FEATURES, HORIZON_STEPS_RANGE, prepare_multi_horizon_dataset

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

PARAMS = dict(
    n_estimators=400,
    learning_rate=0.05,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    tree_method="hist",
    enable_categorical=True,
    n_jobs=2,
    random_state=42,
)


def metrics_pp(y_true, y_pred) -> tuple[float, float]:
    """MAE/RMSE u procentnim poenima zauzetosti."""
    error_pp = (y_pred - y_true) * 100
    mae = float(np.abs(error_pp).mean())
    rmse = float(np.sqrt((error_pp**2).mean()))
    return mae, rmse


def main(city: str = "norfolk") -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Gradim trening/test skup za {len(HORIZON_STEPS_RANGE)} horizonata "
          f"(30 do {30 * HORIZON_STEPS_RANGE[-1]} min)...")
    train_df, test_df = prepare_multi_horizon_dataset(city, HORIZON_STEPS_RANGE)
    print(f"Train: {len(train_df)} redova, Test: {len(test_df)} redova")

    model = xgb.XGBRegressor(**PARAMS)
    model.fit(train_df[FEATURES], train_df["target"])

    carpark_categories = train_df["carpark"].cat.categories.tolist()

    pred = np.clip(model.predict(test_df[FEATURES]), 0, 1)
    overall_mae, overall_rmse = metrics_pp(test_df["target"].values, pred)
    print(f"\nUkupno (svi horizonti): MAE = {overall_mae:.2f} p.p., RMSE = {overall_rmse:.2f} p.p.")

    model_path = os.path.join(os.path.dirname(__file__), f"model_{city}.joblib")
    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "horizon_steps_range": HORIZON_STEPS_RANGE,
            "city": city,
            "carpark_categories": carpark_categories,
        },
        model_path,
    )
    print(f"Model sacuvan: {model_path}")

    # Metrike po horizontu (agregirano preko svih parkinga).
    test_eval = test_df[["carpark", "horizon_minutes"]].copy()
    test_eval["target"] = test_df["target"].values
    test_eval["pred"] = pred

    summary_rows = []
    for horizon_minutes, group in test_eval.groupby("horizon_minutes"):
        mae, rmse = metrics_pp(group["target"].values, group["pred"].values)
        summary_rows.append({"horizon_minutes": int(horizon_minutes), "MAE": round(mae, 2), "RMSE": round(rmse, 2), "n_test": len(group)})
    summary_df = pd.DataFrame(summary_rows).sort_values("horizon_minutes")
    summary_path = os.path.join(OUTPUT_DIR, f"{city}_metrike.csv")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"\nMetrike po horizontu sacuvane: {summary_path}")
    print(summary_df.to_string(index=False))

    # MAE po parkingu x horizontu (koristi se kao "pouzdanost prognoze" na mapi).
    test_eval["ae"] = (test_eval["pred"] - test_eval["target"]).abs() * 100
    per_park = (
        test_eval.groupby(["carpark", "horizon_minutes"], observed=True)["ae"]
        .mean()
        .round(2)
        .unstack("horizon_minutes")
        .sort_index()
    )
    per_park_path = os.path.join(OUTPUT_DIR, f"{city}_mae_po_parkingu.csv")
    per_park.to_csv(per_park_path, encoding="utf-8-sig")
    print(f"\nMAE po parkingu x horizontu (minuti) sacuvan: {per_park_path}")


if __name__ == "__main__":
    main()
