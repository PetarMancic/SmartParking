"""
Pomocna skripta za seminarski rad - generise grafike koji se koriste u radu
(docs/seminarski-rad/assets/). Ne dira postojeci ml/backend kod, samo cita
model.joblib i parking.csv da bi nacrtala grafike.
"""

import os

import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

BASE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.join(BASE_DIR, "..", "..")
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "parking.csv")
MODEL_PATH = os.path.join(PROJECT_ROOT, "ml", "model.joblib")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

plt.rcParams.update({"font.size": 11})


def load_test_split():
    df = pd.read_csv(DATA_PATH)
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"])
    df = df.sort_values("LastUpdated").reset_index(drop=True)
    df["Hour"] = df["LastUpdated"].dt.hour
    df["Minute"] = df["LastUpdated"].dt.minute
    df["DayOfWeekNum"] = df["LastUpdated"].dt.dayofweek

    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    park_encoder = bundle["park_encoder"]
    features = bundle["features"]

    df["ParkEncoded"] = park_encoder.transform(df["SystemCodeNumber"])

    split_index = int(len(df) * 0.8)
    train_df = df.iloc[:split_index]
    test_df = df.iloc[split_index:]

    X_train, y_train = train_df[features], train_df["OccupancyRate"]
    X_test, y_test = test_df[features], test_df["OccupancyRate"]

    return model, X_train, y_train, X_test, y_test, features


def chart_rmse_mae(model, X_train, y_train, X_test, y_test):
    baseline_pred = np.full(len(y_test), y_train.mean())
    xgb_pred = model.predict(X_test)

    baseline_rmse = np.sqrt(mean_squared_error(y_test, baseline_pred))
    baseline_mae = mean_absolute_error(y_test, baseline_pred)
    xgb_rmse = np.sqrt(mean_squared_error(y_test, xgb_pred))
    xgb_mae = mean_absolute_error(y_test, xgb_pred)

    labels = ["RMSE", "MAE"]
    baseline_vals = [baseline_rmse, baseline_mae]
    xgb_vals = [xgb_rmse, xgb_mae]

    x = np.arange(len(labels))
    width = 0.32

    fig, ax = plt.subplots(figsize=(6, 4))
    bars1 = ax.bar(x - width / 2, baseline_vals, width, label="Baseline (prosek)", color="#a3a3a3")
    bars2 = ax.bar(x + width / 2, xgb_vals, width, label="XGBoost", color="#2563eb")

    ax.set_ylabel("Greska (procentni poeni OccupancyRate)")
    ax.set_title("Poredjenje greske: baseline vs. XGBoost (test skup)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.bar_label(bars1, fmt="%.2f", padding=3)
    ax.bar_label(bars2, fmt="%.2f", padding=3)
    ax.set_ylim(0, max(baseline_vals) * 1.25)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "rmse_mae_comparison.png"), dpi=160)
    plt.close(fig)
    print(f"baseline RMSE={baseline_rmse:.3f} MAE={baseline_mae:.3f}")
    print(f"xgboost  RMSE={xgb_rmse:.3f} MAE={xgb_mae:.3f}")


def chart_feature_importance(model, features):
    importances = model.feature_importances_
    order = np.argsort(importances)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(np.array(features)[order], importances[order], color="#2563eb")
    ax.set_xlabel("Znacaj feature-a (XGBoost gain)")
    ax.set_title("Znacaj feature-a u modelu za predikciju")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "feature_importance.png"), dpi=160)
    plt.close(fig)


def chart_predicted_vs_actual(model, X_test, y_test):
    y_pred = model.predict(X_test)

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.scatter(y_test, y_pred, alpha=0.25, s=12, color="#2563eb")
    lims = [0, 100]
    ax.plot(lims, lims, color="#dc2626", linewidth=1.5, linestyle="--", label="Idealna predikcija")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("Stvarna popunjenost (%)")
    ax.set_ylabel("Predvidjena popunjenost (%)")
    ax.set_title("Predvidjeno vs. stvarno (test skup)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "predicted_vs_actual.png"), dpi=160)
    plt.close(fig)


def chart_model_comparison(X_train, y_train, X_test, y_test, xgb_model):
    baseline_pred = np.full(len(y_test), y_train.mean())

    lin = LinearRegression()
    lin.fit(X_train, y_train)
    lin_pred = lin.predict(X_test)

    rf = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)

    xgb_pred = xgb_model.predict(X_test)

    models = [
        ("Baseline\n(prosek)", baseline_pred),
        ("Linear\nRegression", lin_pred),
        ("Random\nForest", rf_pred),
        ("XGBoost", xgb_pred),
    ]

    rmses = [np.sqrt(mean_squared_error(y_test, pred)) for _, pred in models]
    maes = [mean_absolute_error(y_test, pred) for _, pred in models]
    labels = [name for name, _ in models]

    x = np.arange(len(labels))
    width = 0.32

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    bars1 = ax.bar(x - width / 2, rmses, width, label="RMSE", color="#2563eb")
    bars2 = ax.bar(x + width / 2, maes, width, label="MAE", color="#93c5fd")
    ax.set_ylabel("Greska (procentni poeni OccupancyRate)")
    ax.set_title("Poredjenje modela: baseline, linearna regresija, random forest, XGBoost")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.bar_label(bars1, fmt="%.1f", padding=3)
    ax.bar_label(bars2, fmt="%.1f", padding=3)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "model_comparison.png"), dpi=160)
    plt.close(fig)

    for name, pred in models:
        rmse = np.sqrt(mean_squared_error(y_test, pred))
        mae = mean_absolute_error(y_test, pred)
        print(f"{name.replace(chr(10), ' ')}: RMSE={rmse:.3f} MAE={mae:.3f}")


def chart_occupancy_histogram():
    df = pd.read_csv(DATA_PATH)
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.hist(df["OccupancyRate"], bins=30, color="#2563eb", edgecolor="white", alpha=0.9)
    ax.set_xlabel("OccupancyRate (%)")
    ax.set_ylabel("Broj merenja")
    ax.set_title("Raspodela vrednosti OccupancyRate u celom datasetu")
    ax.axvline(df["OccupancyRate"].mean(), color="#dc2626", linestyle="--", linewidth=1.5,
               label=f"Prosek = {df['OccupancyRate'].mean():.1f}%")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "occupancy_histogram.png"), dpi=160)
    plt.close(fig)


def chart_extrapolation(model, park_encoder, features):
    park_id = "BHMBCCMKT01"
    capacity = 577
    park_encoded = park_encoder.transform([park_id])[0]
    day_num = 0  # Mon

    hours = list(range(24))
    rows = pd.DataFrame(
        [{"Hour": h, "Minute": 0, "DayOfWeekNum": day_num, "ParkEncoded": park_encoded, "Capacity": capacity} for h in hours]
    )[features]
    preds = model.predict(rows)
    preds = np.clip(preds, 0, 100)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(hours, preds, marker="o", color="#2563eb", label="Predikcija modela (0-23h)")
    ax.axvspan(8, 16.5, color="#22c55e", alpha=0.12, label="Opseg pokriven merenjima (~08-16:30h)")
    ax.set_xlabel("Sat u danu")
    ax.set_ylabel("Predviđeni OccupancyRate (%)")
    ax.set_title(f"Predikcija modela van trening opsega — {park_id}, ponedeljak")
    ax.set_xticks(range(0, 24, 2))
    ax.legend(loc="upper left", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "extrapolation.png"), dpi=160)
    plt.close(fig)


def chart_capacity_vs_occupancy():
    df = pd.read_csv(DATA_PATH)
    g = df.groupby("SystemCodeNumber").agg(Capacity=("Capacity", "first"), AvgOcc=("OccupancyRate", "mean"))
    corr = g["Capacity"].corr(g["AvgOcc"])

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.scatter(g["Capacity"], g["AvgOcc"], color="#2563eb", s=45, alpha=0.85)
    ax.set_xlabel("Kapacitet parkinga")
    ax.set_ylabel("Prosečna popunjenost (%)")
    ax.set_title(f"Kapacitet vs. prosečna popunjenost po parkingu (r = {corr:.2f})")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "capacity_vs_occupancy.png"), dpi=160)
    plt.close(fig)
    print(f"capacity vs occupancy correlation: {corr:.3f}")


def chart_day_of_week():
    df = pd.read_csv(DATA_PATH)
    order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    avg = df.groupby("DayOfWeek")["OccupancyRate"].mean().reindex(order)

    fig, ax = plt.subplots(figsize=(6.5, 4))
    colors = ["#2563eb" if d not in ("Sat", "Sun") else "#93c5fd" for d in order]
    bars = ax.bar(order, avg.values, color=colors)
    ax.set_ylabel("Prosečna popunjenost (%)")
    ax.set_title("Prosečna popunjenost po danu u nedelji")
    ax.bar_label(bars, fmt="%.1f", padding=3)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "day_of_week.png"), dpi=160)
    plt.close(fig)


def chart_architecture():
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.axis("off")

    boxes = [
        ("data/\nparking.csv", 0.04),
        ("ml/train.py\n(XGBoost)", 0.28),
        ("ml/model.joblib", 0.52),
        ("backend/\n(FastAPI)", 0.74),
        ("frontend/\n(Next.js + Leaflet)", 0.96),
    ]
    box_w, box_h = 0.16, 0.5
    y = 0.25

    for label, x in boxes:
        rect = plt.Rectangle((x, y), box_w, box_h, facecolor="#eff6ff", edgecolor="#2563eb", linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + box_w / 2, y + box_h / 2, label, ha="center", va="center", fontsize=9.5)

    for i in range(len(boxes) - 1):
        x_start = boxes[i][1] + box_w
        x_end = boxes[i + 1][1]
        ax.annotate(
            "", xy=(x_end, y + box_h / 2), xytext=(x_start, y + box_h / 2),
            arrowprops=dict(arrowstyle="->", color="#2563eb", linewidth=1.5),
        )

    ax.set_xlim(0, 1.14)
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS_DIR, "architecture_flow.png"), dpi=160)
    plt.close(fig)


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    model, X_train, y_train, X_test, y_test, features = load_test_split()
    chart_rmse_mae(model, X_train, y_train, X_test, y_test)
    chart_feature_importance(model, features)
    chart_predicted_vs_actual(model, X_test, y_test)
    chart_model_comparison(X_train, y_train, X_test, y_test, model)
    chart_occupancy_histogram()
    chart_capacity_vs_occupancy()
    chart_day_of_week()
    bundle = joblib.load(MODEL_PATH)
    chart_extrapolation(bundle["model"], bundle["park_encoder"], bundle["features"])
    chart_architecture()
    print("Grafici sacuvani u", ASSETS_DIR)


if __name__ == "__main__":
    main()
