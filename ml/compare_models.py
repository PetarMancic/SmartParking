"""
Korak 4 (PLAN_ZAVRSETKA.md) - poredjenje modela za predikciju zauzetosti.

Pitanje: zasto XGBoost? Svi modeli dobijaju ISTE podatke (svih 31 horizonata,
30 min do 15,5 h), ISTE ulaze (ml/data_prep.py FEATURES) i ISTU hronolosku
podelu (trening pre 1.10.2017, test 1.10.-5.12.2017).

Baseline-ovi (bez treninga):
  - poslednja vrednost:   zauzetost ostaje kao sada (y_t)
  - pre nedelju dana:     isto ciljno vreme nedelju dana ranije (y_lastweek);
                          gde fali, koristi se poslednja vrednost
  - tipicna kriva:        prosek iz treninga po (parking, dan u nedelji, slot)
Modeli:
  - Ridge:                linearna regresija sa L2 regularizacijom; rupe u
                          lag ulazima popunjene medijanom (+ indikator rupe),
                          parking / dan / sat kao one-hot
  - Random Forest:        prosek mnogo stabala (bagging), rupe podrzane
  - HistGradientBoosting: boosting iz scikit-learn-a - da se vidi da li je
                          presudan bas XGBoost ili porodica algoritama
  - XGBoost:              model koji aplikacija stvarno koristi
                          (ml/model_norfolk.joblib), ne novi trening

Izlaz: ml/output/poredjenje_modela.csv (ukupno + vreme treninga/predikcije),
ml/output/poredjenje_modela_po_horizontu.csv, ml/output/poredjenje_modela.png

Pokretanje (iz korena projekta):
    python ml/compare_models.py
"""

from __future__ import annotations

import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.data_prep import FEATURES, HORIZON_STEPS_RANGE, prepare_multi_horizon_dataset  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_norfolk.joblib")
CITY = "norfolk"
SEED = 42

# Horizonti koji idu u kratku tabelu u konzoli (ceo opseg je u CSV-u).
REPORT_HORIZONS_MIN = [30, 60, 120, 240, 480, 900]

LAG_COLUMNS = ["y_t", "y_t1", "y_t2", "delta", "y_yesterday", "y_lastweek"]
NUMERIC_COLUMNS = LAG_COLUMNS + ["capacity", "horizon_minutes", "weekend", "holiday"]
ONE_HOT_COLUMNS = ["carpark", "dow", "hour"]


def metrics_pp(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    """MAE/RMSE u procentnim poenima zauzetosti (isto kao ml/train_norfolk.py)."""
    error_pp = (np.clip(y_pred, 0, 1) - y_true) * 100
    return float(np.abs(error_pp).mean()), float(np.sqrt((error_pp**2).mean()))


# ---------------------------------------------------------------- baseline-ovi

def baseline_last_value(_train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    return test["y_t"].to_numpy()


def baseline_last_week(_train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    return test["y_lastweek"].fillna(test["y_t"]).to_numpy()


def baseline_typical(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    # Jedan horizont je dovoljan - isti ciljni trenutak se inace ponavlja 31 put.
    one_horizon = train[train["horizon_minutes"] == 30]
    keys = ["carpark", "dow", "hour"]
    typical = one_horizon.groupby(keys, observed=True)["target"].mean().rename("typical")
    merged = test[keys].join(typical, on=keys)
    return merged["typical"].fillna(one_horizon["target"].mean()).to_numpy()


# --------------------------------------------------------------------- modeli

def make_ridge() -> Pipeline:
    preprocess = ColumnTransformer(
        [
            ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), NUMERIC_COLUMNS),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ONE_HOT_COLUMNS),
        ]
    )
    return make_pipeline(preprocess, Ridge(alpha=1.0))


def ridge_input(frame: pd.DataFrame) -> pd.DataFrame:
    x = frame[FEATURES].copy()
    x["carpark"] = x["carpark"].astype(str)
    return x


def make_random_forest() -> RandomForestRegressor:
    # max_samples: svako stablo vidi 10% trening skupa (~200 hiljada redova) -
    # inace bi 100 stabala na ~2M redova trajalo predugo za ovo poredjenje.
    return RandomForestRegressor(
        n_estimators=100, max_features=0.5, min_samples_leaf=5, max_samples=0.1, n_jobs=-1, random_state=SEED
    )


def tree_input(frame: pd.DataFrame) -> pd.DataFrame:
    # Random Forest ne razume pandas kategorije - parking ide kao celobrojni kod.
    x = frame[FEATURES].copy()
    x["carpark"] = x["carpark"].cat.codes
    return x


def make_hist_gb() -> HistGradientBoostingRegressor:
    # Isti budzet kao XGBoost u ml/train_norfolk.py (400 iteracija, korak 0.05).
    return HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_depth=6, categorical_features="from_dtype", random_state=SEED
    )


def run_baselines(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, dict]:
    results = {}
    for name, fn in [
        ("poslednja vrednost", baseline_last_value),
        ("pre nedelju dana", baseline_last_week),
        ("tipicna kriva", baseline_typical),
    ]:
        start = time.perf_counter()
        pred = fn(train, test)
        results[name] = {"pred": pred, "train_s": 0.0, "predict_s": time.perf_counter() - start, "kind": "baseline"}
    return results


def run_models(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, dict]:
    results = {}
    specs = [
        ("Ridge", make_ridge, ridge_input),
        ("Random Forest", make_random_forest, tree_input),
        ("HistGradientBoosting", make_hist_gb, lambda f: f[FEATURES]),
    ]
    for name, make, to_input in specs:
        print(f"  trening: {name}...")
        model = make()
        start = time.perf_counter()
        model.fit(to_input(train), train["target"])
        train_s = time.perf_counter() - start
        start = time.perf_counter()
        pred = model.predict(to_input(test))
        results[name] = {"pred": pred, "train_s": train_s, "predict_s": time.perf_counter() - start, "kind": "model"}
        print(f"    {train_s:.0f} s trening")

    # XGBoost: model iz aplikacije. Vreme treninga nije mereno ovde (model je
    # vec istreniran u ml/train_norfolk.py) - meri se samo predikcija.
    bundle = joblib.load(MODEL_PATH)
    x = test[bundle["features"]].copy()
    x["carpark"] = pd.Categorical(x["carpark"].astype(str), categories=bundle["carpark_categories"])
    start = time.perf_counter()
    pred = bundle["model"].predict(x)
    results["XGBoost"] = {"pred": pred, "train_s": np.nan, "predict_s": time.perf_counter() - start, "kind": "model"}
    return results


# -------------------------------------------------------------------- grafik

# Boje: validirana kategorijska paleta (dataviz skill, --pairs all: PASS) za 4
# naucena modela; baseline-ovi su sivi (referenca), razlikuju se crtom i
# markerom. Identitet nikad samo bojom - legenda + oblik markera + tip crte.
# "poslednja vrednost" nije na grafiku: raste do ~34 p.p. i spljostila bi
# razlike medju modelima (3-7 p.p.); ostaje u tabeli.
PLOT_STYLE = {
    "XGBoost": {"color": "#2a78d6", "marker": "o", "linestyle": "-"},
    "HistGradientBoosting": {"color": "#1baf7a", "marker": "D", "linestyle": "-"},
    "Random Forest": {"color": "#e87ba4", "marker": "v", "linestyle": "-"},
    "Ridge": {"color": "#eda100", "marker": "s", "linestyle": "-"},
    "pre nedelju dana": {"color": "#898781", "marker": "s", "linestyle": "--"},
    "tipicna kriva": {"color": "#898781", "marker": "x", "linestyle": "-."},
}
INK, MUTED, GRID = "#21201c", "#52514e", "#e4e3dc"
ZOOM_MAX_HOURS = 4
DISPLAY_NAME = {"tipicna kriva": "tipična kriva"}


def _style_axes(ax) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_xlabel("Horizont predikcije (h)", fontsize=9, color=MUTED)


def plot_by_horizon(by_horizon: pd.DataFrame) -> None:
    """Levo: ceo opseg horizonata. Desno: uvecano do 4 h, gde su razlike
    izmedju modela sa stablima najvece (i gde se aplikacija najvise koristi)."""
    import matplotlib.pyplot as plt

    fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [2, 1]})
    for name, style in PLOT_STYLE.items():
        s = by_horizon[by_horizon["model"] == name].sort_values("horizon_minutes")
        hours = s["horizon_minutes"] / 60
        label = DISPLAY_NAME.get(name, name)
        common = dict(color=style["color"], linestyle=style["linestyle"], linewidth=2, marker=style["marker"], label=label)
        ax_full.plot(hours, s["MAE"], markersize=5, markevery=4, **common)
        near = hours <= ZOOM_MAX_HOURS
        ax_zoom.plot(hours[near], s["MAE"][near], markersize=6, **common)

    ax_full.set_title("Greška po horizontu · Norfolk, test 1.10.–5.12.2017", fontsize=10, color=INK, loc="left")
    ax_full.set_ylabel("MAE (procentni poeni zauzetosti)", fontsize=9, color=MUTED)
    ax_full.set_xticks(range(0, 17, 2))
    ax_full.set_ylim(0, 10.5)
    _style_axes(ax_full)

    ax_zoom.set_title(f"Uvećano: do {ZOOM_MAX_HOURS} h", fontsize=10, color=INK, loc="left")
    ax_zoom.set_xticks([0.5, 1, 2, 3, 4])
    ax_zoom.set_ylim(2, 7.5)
    _style_axes(ax_zoom)

    handles, labels = ax_full.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.045), ncol=6, frameon=False, fontsize=9)
    fig.text(
        0.01, 0.008, "„Poslednja vrednost” nije prikazana (5,1 p.p. na 30 min, do 34 p.p. na dužim horizontima) – vidi tabelu.",
        fontsize=7.5, color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    path = os.path.join(OUTPUT_DIR, "poredjenje_modela.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Sacuvan grafik: {path}")


# ---------------------------------------------------------------------- main

def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Gradim trening/test skup ({len(HORIZON_STEPS_RANGE)} horizonata)...")
    train, test = prepare_multi_horizon_dataset(CITY, HORIZON_STEPS_RANGE)
    print(f"Train: {len(train)} redova, Test: {len(test)} redova")
    # Iste kategorije parkinga u oba skupa - inace bi celobrojni kodovi
    # (Random Forest) ili kategorije (HistGradientBoosting) mogli da se razlikuju.
    test["carpark"] = pd.Categorical(test["carpark"].astype(str), categories=train["carpark"].cat.categories)

    results = run_baselines(train, test)
    results.update(run_models(train, test))

    y_true = test["target"].to_numpy()
    overall_rows, horizon_rows = [], []
    for name, r in results.items():
        mae, rmse = metrics_pp(y_true, r["pred"])
        overall_rows.append(
            {
                "model": name,
                "vrsta": r["kind"],
                "MAE": round(mae, 2),
                "RMSE": round(rmse, 2),
                "trening_s": round(r["train_s"], 1),
                "predikcija_s": round(r["predict_s"], 2),
                "predikcija_us_po_redu": round(1e6 * r["predict_s"] / len(test), 2),
            }
        )
        frame = pd.DataFrame({"h": test["horizon_minutes"].to_numpy(), "y": y_true, "p": r["pred"]})
        for horizon, g in frame.groupby("h"):
            h_mae, h_rmse = metrics_pp(g["y"].to_numpy(), g["p"].to_numpy())
            horizon_rows.append(
                {"model": name, "horizon_minutes": int(horizon), "MAE": round(h_mae, 2), "RMSE": round(h_rmse, 2), "n_test": len(g)}
            )

    overall = pd.DataFrame(overall_rows).sort_values("MAE")
    by_horizon = pd.DataFrame(horizon_rows)
    overall.to_csv(os.path.join(OUTPUT_DIR, "poredjenje_modela.csv"), index=False, encoding="utf-8-sig")
    by_horizon.to_csv(os.path.join(OUTPUT_DIR, "poredjenje_modela_po_horizontu.csv"), index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 200)
    print("\n=== Ukupno (svi horizonti) ===")
    print(overall.to_string(index=False))
    print("\n=== MAE po horizontu (p.p.) ===")
    pivot = by_horizon.pivot(index="model", columns="horizon_minutes", values="MAE")
    print(pivot[REPORT_HORIZONS_MIN].loc[overall["model"]].to_string())

    plot_by_horizon(by_horizon)


if __name__ == "__main__":
    main()
