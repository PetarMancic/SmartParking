"""
Korak 5 (PLAN_ZAVRSETKA.md) - analiza modela za predikciju zauzetosti.

Sve se radi na istoj hronoloskoj podeli kao u koraku 4 (trening pre
1.10.2017, test 1.10.-5.12.2017, svih 31 horizonata). Delovi:

  doprinos      - koliko svaki ulaz doprinosi predikciji (SHAP vrednosti iz
                  samog XGBoost-a: booster.predict(pred_contribs=True), bez
                  dodatne biblioteke), posebno za kratke i duge horizonte
  greske        - greska po parkingu, tipu parkinga, dobu dana, danu u
                  nedelji i po tome koliko je parking stvarno pun
  nedostajuci   - sta se desava kad deo ulaza fali (npr. nema merenja od
                  pre nedelju dana) i da li pomaze zamena (fallback)
  ablacija      - ponovni trening bez pojedinih grupa ulaza
  duzina        - ponovni trening na 2 nedelje / 1 / 3 / 6 / ~11 meseci
  specijalizovani - jedan model za sve horizonte naspram posebnog modela za
                  30 min, 1 h i 2 h

Delovi doprinos/greske/nedostajuci koriste model iz aplikacije
(ml/model_norfolk.joblib). Ablacija/duzina/specijalizovani treniraju nove
modele sa ISTIM hiperparametrima (procitanim iz sacuvanog modela).

Izlaz: ml/output/analiza_*.csv i analiza_*.png

Pokretanje (iz korena projekta), svi delovi ili samo neki:
    python ml/analyze_model.py
    python ml/analyze_model.py doprinos greske nedostajuci
"""

from __future__ import annotations

import json
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.compare_models import baseline_typical, metrics_pp  # noqa: E402
from ml.data_prep import (  # noqa: E402
    CITY_CONFIGS,
    FEATURES,
    HORIZON_STEPS_RANGE,
    load_raw,
    prepare_multi_horizon_dataset,
    resample_per_park,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_norfolk.joblib")
PARKS_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "carparks_norfolk.json")
CITY = "norfolk"
SEED = 42
TEST_START = CITY_CONFIGS[CITY]["test_start"]

# Broj niti pri ponovnom treningu - menja samo brzinu, ne i model.
TRAIN_N_JOBS = 8

REPORT_HORIZONS_MIN = [30, 60, 120, 240, 480, 900]

# Grupe horizonata za doprinos ulaza.
HORIZON_GROUPS = [("do 2 h", 30, 120), ("2–8 h", 150, 480), ("preko 8 h", 510, 930)]
SHAP_ROWS_PER_GROUP = 15000

CURRENT_STATE = ["y_t", "y_t1", "y_t2", "delta"]
SAME_SLOT_BEFORE = ["y_yesterday", "y_lastweek"]
ABLATIONS = {
    "pun model": [],
    "bez trenutnog stanja": CURRENT_STATE,
    "bez istog termina ranije": SAME_SLOT_BEFORE,
    "samo kalendar i parking": CURRENT_STATE + SAME_SLOT_BEFORE,
    "bez identiteta parkinga": ["carpark", "capacity"],
    "bez praznika": ["holiday"],
}

TRAIN_WINDOWS = {
    "2 nedelje": pd.Timedelta(days=14),
    "1 mesec": pd.Timedelta(days=30),
    "3 meseca": pd.Timedelta(days=91),
    "6 meseci": pd.Timedelta(days=182),
    "~11 meseci (sve)": None,
}

SPECIALIZED_HORIZONS_MIN = [30, 60, 120]

OCCUPANCY_BANDS = [0, 0.5, 0.8, 0.95, 1.0001]
OCCUPANCY_BAND_LABELS = ["< 50%", "50–80%", "80–95%", "≥ 95%"]

FEATURE_LABELS = {
    "y_t": "zauzetost sada (y_t)",
    "y_t1": "pre 30 min (y_t1)",
    "y_t2": "pre 1 h (y_t2)",
    "delta": "promena za 30 min (delta)",
    "y_yesterday": "isti termin juče (y_yesterday)",
    "y_lastweek": "isti termin pre 7 dana (y_lastweek)",
    "hour": "doba dana (hour)",
    "dow": "dan u nedelji (dow)",
    "weekend": "vikend (weekend)",
    "holiday": "praznik (holiday)",
    "carpark": "parking (carpark)",
    "capacity": "kapacitet (capacity)",
    "horizon_minutes": "horizont (horizon_minutes)",
}


# ------------------------------------------------------------- zajednicko

def load_bundle() -> dict:
    return joblib.load(MODEL_PATH)


def model_input(bundle: dict, frame: pd.DataFrame) -> pd.DataFrame:
    x = frame[bundle["features"]].copy()
    x["carpark"] = pd.Categorical(x["carpark"].astype(str), categories=bundle["carpark_categories"])
    return x


def predict(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    return np.clip(bundle["model"].predict(model_input(bundle, frame)), 0, 1)


def mae_pp(y_true, y_pred) -> float:
    return metrics_pp(np.asarray(y_true), np.asarray(y_pred))[0]


def park_types() -> dict[str, str]:
    """Tip parkinga iz data/carparks_norfolk.json (grad / Park & Ride /
    ostalo); parking bez tipa u JSON-u je 'nepoznat'."""
    with open(PARKS_JSON, encoding="utf-8") as f:
        parks = json.load(f)["parks"]
    return {p["code"]: (p.get("type") or "nepoznat") for p in parks}


def park_names() -> dict[str, str]:
    with open(PARKS_JSON, encoding="utf-8") as f:
        parks = json.load(f)["parks"]
    return {p["code"]: p.get("name") or "" for p in parks}


def retrain_params(bundle: dict) -> dict:
    """Hiperparametri sacuvanog modela - ponovni trening je uporediv sa njim."""
    params = bundle["model"].get_params()
    params["n_jobs"] = TRAIN_N_JOBS
    return params


def train_and_predict(params: dict, train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, float]:
    model = xgb.XGBRegressor(**params)
    start = time.perf_counter()
    model.fit(train[features], train["target"])
    seconds = time.perf_counter() - start
    return np.clip(model.predict(test[features]), 0, 1), seconds


def mae_by_horizon(test: pd.DataFrame, pred: np.ndarray) -> dict[int, float]:
    frame = pd.DataFrame({"h": test["horizon_minutes"].to_numpy(), "y": test["target"].to_numpy(), "p": pred})
    return {int(h): mae_pp(g["y"], g["p"]) for h, g in frame.groupby("h")}


# ------------------------------------------------------------------ grafici

INK, MUTED, GRID = "#21201c", "#52514e", "#e4e3dc"
# Tip parkinga: plavo/narandzasto (validirano); "ostalo" (B&Q Boundary Road,
# jedan parking) i "nepoznat" namerno sivo (neutralno) i uvek uz drugaciju
# crtu / legendu.
TYPE_STYLE = {
    "grad": {"color": "#2a78d6", "linestyle": "-", "marker": "o"},
    "Park & Ride": {"color": "#eb6834", "linestyle": "-", "marker": "s"},
    "ostalo": {"color": "#898781", "linestyle": "--", "marker": "x"},
    "nepoznat": {"color": "#898781", "linestyle": ":", "marker": "x"},
}
# Grupe horizonata su uredjene (kratko -> dugo): jedna nijansa, svetlo -> tamno
# (ordinalna rampa, validirana sa --ordinal).
HORIZON_GROUP_COLORS = ["#86b6ef", "#2a78d6", "#104281"]
# Ablacija: validirana kategorijska paleta iz koraka 4 (--pairs all: PASS).
ABLATION_STYLE = {
    "pun model": {"color": "#2a78d6", "marker": "o"},
    "bez trenutnog stanja": {"color": "#eda100", "marker": "s"},
    "bez istog termina ranije": {"color": "#1baf7a", "marker": "D"},
    "samo kalendar i parking": {"color": "#e87ba4", "marker": "v"},
}


def _style_axes(ax, grid_axis: str = "y") -> None:
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)


def _save(fig, name: str) -> None:
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=200)
    print(f"Sacuvan grafik: {path}")


# ---------------------------------------------------------------- doprinos

def part_contributions(bundle: dict, test: pd.DataFrame) -> None:
    """Prosecna apsolutna SHAP vrednost po ulazu, u procentnim poenima: za
    koliko p.p. taj ulaz u proseku pomera predikciju u odnosu na prosek."""
    booster = bundle["model"].get_booster()
    rows = []
    for group, low, high in HORIZON_GROUPS:
        part = test[(test["horizon_minutes"] >= low) & (test["horizon_minutes"] <= high)]
        sample = part.sample(n=min(SHAP_ROWS_PER_GROUP, len(part)), random_state=SEED)
        matrix = xgb.DMatrix(model_input(bundle, sample), enable_categorical=True)
        contributions = booster.predict(matrix, pred_contribs=True)[:, :-1]  # poslednja kolona = prosek (bias)
        mean_abs = np.abs(contributions).mean(axis=0) * 100
        for feature, value in zip(bundle["features"], mean_abs):
            rows.append({"grupa_horizonata": group, "feature": feature, "doprinos_pp": round(float(value), 3)})

    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(OUTPUT_DIR, "analiza_doprinos.csv"), index=False, encoding="utf-8-sig")
    pivot = table.pivot(index="feature", columns="grupa_horizonata", values="doprinos_pp")[[g for g, _, _ in HORIZON_GROUPS]]
    pivot = pivot.loc[pivot.mean(axis=1).sort_values(ascending=False).index]
    print("\n=== Doprinos ulaza: prosecna |SHAP| vrednost (p.p.) ===")
    print(pivot.round(2).to_string())
    plot_contributions(pivot)


def plot_contributions(pivot: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    features = list(pivot.index)[::-1]  # najvazniji gore
    positions = np.arange(len(features))
    bar_height = 0.26
    for i, (group, color) in enumerate(zip(pivot.columns, HORIZON_GROUP_COLORS)):
        offset = (1 - i) * bar_height
        ax.barh(positions + offset, pivot.loc[features, group], height=bar_height - 0.03, color=color, label=f"horizont {group}")
    ax.set_yticks(positions)
    ax.set_yticklabels([FEATURE_LABELS.get(f, f) for f in features], fontsize=9, color=INK)
    ax.set_xlabel("Prosečan uticaj na predikciju (|SHAP|, procentni poeni)", fontsize=9, color=MUTED)
    ax.set_title("Šta model koristi · Norfolk, test 1.10.–5.12.2017", fontsize=10, color=INK, loc="left")
    _style_axes(ax, grid_axis="x")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout()
    _save(fig, "analiza_doprinos.png")
    plt.close(fig)


# ------------------------------------------------------------------ greske

def part_errors(bundle: dict, test: pd.DataFrame) -> None:
    types = park_types()
    names = park_names()
    frame = pd.DataFrame(
        {
            "carpark": test["carpark"].astype(str).to_numpy(),
            "horizon_minutes": test["horizon_minutes"].to_numpy(),
            "target_time": test["target_time"].to_numpy(),
            "y": test["target"].to_numpy(),
            "p": predict(bundle, test),
        }
    )
    frame["ae"] = (frame["p"] - frame["y"]).abs() * 100
    frame["tip"] = frame["carpark"].map(types).fillna("nepoznat")
    frame["sat"] = pd.to_datetime(frame["target_time"]).dt.hour
    frame["dan"] = pd.to_datetime(frame["target_time"]).dt.dayofweek

    per_park = (
        frame.groupby("carpark")
        .agg(tip=("tip", "first"), MAE=("ae", "mean"), prosecna_zauzetost_pct=("y", "mean"), n=("ae", "size"))
        .assign(prosecna_zauzetost_pct=lambda d: d["prosecna_zauzetost_pct"] * 100)
        .round(2)
        .sort_values("MAE", ascending=False)
    )
    per_park.insert(0, "naziv", [names.get(c, "") for c in per_park.index])
    per_park["MAE_30min"] = frame[frame["horizon_minutes"] == 30].groupby("carpark")["ae"].mean().round(2)
    per_type = frame.groupby("tip").agg(MAE=("ae", "mean"), prosecna_zauzetost_pct=("y", "mean"), n=("ae", "size"))
    per_type["prosecna_zauzetost_pct"] *= 100
    per_hour = frame.groupby(["tip", "sat"])["ae"].mean().unstack("tip")
    per_day = frame.groupby("dan")["ae"].mean().rename(index=dict(enumerate(["pon", "uto", "sre", "čet", "pet", "sub", "ned"])))
    frame["pun"] = pd.cut(frame["y"], OCCUPANCY_BANDS, labels=OCCUPANCY_BAND_LABELS, right=False)
    per_band = frame.groupby("pun", observed=True).agg(MAE=("ae", "mean"), n=("ae", "size"))
    per_band["udeo_pct"] = 100 * per_band["n"] / len(frame)
    # Za preporuku je bitno: kad je parking stvarno skoro pun, da li model to vidi?
    near_full = frame[frame["y"] >= 0.95]
    predicted_full_share = 100 * (near_full["p"] >= 0.90).mean()

    per_park.to_csv(os.path.join(OUTPUT_DIR, "analiza_greska_po_parkingu.csv"), encoding="utf-8-sig")
    per_hour.round(2).to_csv(os.path.join(OUTPUT_DIR, "analiza_greska_po_satu.csv"), encoding="utf-8-sig")
    per_band.round(2).to_csv(os.path.join(OUTPUT_DIR, "analiza_greska_po_popunjenosti.csv"), encoding="utf-8-sig")

    pd.set_option("display.width", 200)
    print("\n=== Greska po parkingu (svi horizonti, p.p.) ===")
    print(per_park.to_string())
    print("\n=== Greska po tipu parkinga ===")
    print(per_type.round(2).to_string())
    print("\n=== Greska po danu u nedelji (ciljni dan) ===")
    print(per_day.round(2).to_string())
    print("\n=== Greska po stvarnoj popunjenosti ===")
    print(per_band.round(2).to_string())
    print(f"Kad je parking stvarno >= 95% pun, model predvidja >= 90% u {predicted_full_share:.1f}% slucajeva")

    plot_errors(per_hour, per_park)


def plot_errors(per_hour: pd.DataFrame, per_park: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    fig, (ax_hour, ax_park) = plt.subplots(1, 2, figsize=(11.5, 4.8), gridspec_kw={"width_ratios": [1.1, 1]})

    for park_type, style in TYPE_STYLE.items():
        if park_type not in per_hour:
            continue
        s = per_hour[park_type].dropna()
        ax_hour.plot(s.index, s.values, linewidth=2, markersize=5, label=park_type, **style)
    ax_hour.set_title("Greška po dobu dana (ciljni sat)", fontsize=10, color=INK, loc="left")
    ax_hour.set_xlabel("Sat u danu", fontsize=9, color=MUTED)
    ax_hour.set_ylabel("MAE (procentni poeni zauzetosti)", fontsize=9, color=MUTED)
    ax_hour.set_xticks(range(8, 24, 2))
    ax_hour.set_ylim(bottom=0)
    _style_axes(ax_hour)
    ax_hour.legend(frameon=False, fontsize=9, loc="upper left")

    ordered = per_park.sort_values("MAE")
    colors = [TYPE_STYLE.get(t, TYPE_STYLE["nepoznat"])["color"] for t in ordered["tip"]]
    labels = [f"{code} {name}".strip() for code, name in zip(ordered.index, ordered["naziv"])]
    ax_park.barh(range(len(ordered)), ordered["MAE"], color=colors, height=0.7)
    ax_park.set_yticks(range(len(ordered)))
    ax_park.set_yticklabels(labels, fontsize=8, color=INK)
    for i, (mae, occupancy) in enumerate(zip(ordered["MAE"], ordered["prosecna_zauzetost_pct"])):
        ax_park.text(mae + 0.15, i, f"{mae:.1f}  (prosek {occupancy:.0f}%)", va="center", fontsize=7.5, color=MUTED)
    ax_park.set_title("Greška po parkingu (boja = tip)", fontsize=10, color=INK, loc="left")
    ax_park.set_xlabel("MAE (p.p.), svi horizonti", fontsize=9, color=MUTED)
    ax_park.set_xlim(0, ordered["MAE"].max() * 1.45)
    _style_axes(ax_park, grid_axis="x")

    fig.suptitle("Norfolk, test 1.10.–5.12.2017", fontsize=9, color=MUTED, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    _save(fig, "analiza_greske.png")
    plt.close(fig)


# ------------------------------------------------------------ nedostajuci

def value_days_before(frame: pd.DataFrame, series: dict[str, pd.Series], days: int) -> np.ndarray:
    """Stvarna zauzetost istog parkinga u ciljnom terminu `days` dana ranije
    (NaN ako tada nema merenja). Za days=7 je to bas y_lastweek."""
    out = np.full(len(frame), np.nan)
    target_times = frame["target_time"].to_numpy()
    for park_id, positions in frame.groupby("carpark", observed=True).indices.items():
        times = pd.DatetimeIndex(target_times[positions]) - pd.Timedelta(days=days)
        out[positions] = series[str(park_id)].reindex(times).to_numpy()
    return out


def with_lastweek(frame: pd.DataFrame, values: np.ndarray) -> pd.DataFrame:
    changed = frame.copy()
    changed["y_lastweek"] = values
    return changed


def part_missing(bundle: dict, train: pd.DataFrame, test: pd.DataFrame) -> None:
    series = resample_per_park(load_raw(CITY))
    typical = baseline_typical(train, test)
    two_weeks = value_days_before(test, series, 14)

    lags = CURRENT_STATE[1:] + SAME_SLOT_BEFORE  # y_t uvek postoji (inace nema predikcije)
    complete = test[lags].notna().all(axis=1).to_numpy()
    groups = {
        "svi ulazi postoje": complete,
        "fali y_lastweek": test["y_lastweek"].isna().to_numpy(),
        "fali y_yesterday": test["y_yesterday"].isna().to_numpy(),
        "fali y_t1 ili y_t2": test[["y_t1", "y_t2"]].isna().any(axis=1).to_numpy(),
    }
    pred = predict(bundle, test)
    y = test["target"].to_numpy()

    # 1) Prirodne rupe: tipicna kriva na istim redovima pokazuje da li su ti
    #    redovi sami po sebi tezi (npr. neobican dan), ili model greska zbog rupe.
    natural = []
    for name, mask in groups.items():
        natural.append(
            {
                "redovi": name,
                "n": int(mask.sum()),
                "udeo_pct": round(100 * mask.mean(), 2),
                "MAE_model": round(mae_pp(y[mask], pred[mask]), 2),
                "MAE_tipicna_kriva": round(mae_pp(y[mask], typical[mask]), 2),
            }
        )
    natural = pd.DataFrame(natural)

    # 2) Vestacko brisanje na redovima gde SVE postoji: ista situacija, samo
    #    bez jednog ulaza - cist efekat rupe, bez "teskog dana".
    base = test[complete]
    y_base = base["target"].to_numpy()
    masked_variants = {
        "nista ne fali": base,
        "fali y_lastweek": base.assign(y_lastweek=np.nan),
        "fali y_yesterday": base.assign(y_yesterday=np.nan),
        "fale y_lastweek i y_yesterday": base.assign(y_lastweek=np.nan, y_yesterday=np.nan),
        "fale y_t1, y_t2 (samo trenutno)": base.assign(y_t1=np.nan, y_t2=np.nan, delta=np.nan),
    }
    masked = pd.DataFrame(
        [{"varijanta": name, "MAE_model": round(mae_pp(y_base, predict(bundle, frame)), 2)} for name, frame in masked_variants.items()]
    )

    # 3) Zamena (fallback) za y_lastweek koji fali - samo pri predikciji, bez
    #    novog treninga: (a) isti termin 14 dana ranije, (b) tipicna vrednost
    #    iz treninga, (c) prvo 14 dana, pa tipicna ako ni toga nema.
    def fallbacks(frame: pd.DataFrame, fourteen: np.ndarray, typ: np.ndarray) -> dict[str, pd.DataFrame]:
        return {
            "bez zamene (NaN)": frame,
            "14 dana ranije": with_lastweek(frame, fourteen),
            "tipicna vrednost": with_lastweek(frame, typ),
            "14 dana, pa tipicna": with_lastweek(frame, np.where(np.isnan(fourteen), typ, fourteen)),
        }

    rows = []
    missing = groups["fali y_lastweek"]
    natural_missing = test[missing].assign(y_lastweek=np.nan)
    for name, frame in fallbacks(natural_missing, two_weeks[missing], typical[missing]).items():
        rows.append({"redovi": "prirodno fali y_lastweek", "zamena": name, "MAE_model": mae_pp(y[missing], predict(bundle, frame))})
    for name, frame in fallbacks(base.assign(y_lastweek=np.nan), two_weeks[complete], typical[complete]).items():
        rows.append({"redovi": "vestacki obrisan y_lastweek", "zamena": name, "MAE_model": mae_pp(y_base, predict(bundle, frame))})
    rows.append({"redovi": "vestacki obrisan y_lastweek", "zamena": "(stvarna vrednost - gornja granica)", "MAE_model": mae_pp(y_base, predict(bundle, base))})
    # Ceo test: zamena se primenjuje samo tamo gde y_lastweek fali (kao u backend/predictor.py).
    whole_test = with_lastweek(test, test["y_lastweek"].fillna(pd.Series(two_weeks, index=test.index)).to_numpy())
    rows.append({"redovi": "ceo test", "zamena": "bez zamene (NaN)", "MAE_model": mae_pp(y, pred)})
    rows.append({"redovi": "ceo test", "zamena": "14 dana ranije", "MAE_model": mae_pp(y, predict(bundle, whole_test))})
    fallback = pd.DataFrame(rows).round(2)
    coverage = 100 * np.isfinite(two_weeks[missing]).mean()

    # 4) Dan iz demonstracije: 14.10.2017 (7.10. nema podataka).
    day = (test["target_time"].dt.normalize() == pd.Timestamp("2017-10-14")).to_numpy()
    day_frame = test[day]
    day_fallback = with_lastweek(day_frame, np.where(day_frame["y_lastweek"].isna(), two_weeks[day], day_frame["y_lastweek"]))
    day_rows = pd.DataFrame(
        [
            {"dan": "14.10.2017", "varijanta": "bez zamene", "MAE_model": mae_pp(y[day], predict(bundle, day_frame))},
            {"dan": "14.10.2017", "varijanta": "y_lastweek iz 14 dana ranije", "MAE_model": mae_pp(y[day], predict(bundle, day_fallback))},
            {"dan": "14.10.2017", "varijanta": "tipicna kriva (poredjenja radi)", "MAE_model": mae_pp(y[day], typical[day])},
        ]
    ).round(2)

    natural.to_csv(os.path.join(OUTPUT_DIR, "analiza_nedostajuci_prirodni.csv"), index=False, encoding="utf-8-sig")
    masked.to_csv(os.path.join(OUTPUT_DIR, "analiza_nedostajuci_vestacki.csv"), index=False, encoding="utf-8-sig")
    fallback.to_csv(os.path.join(OUTPUT_DIR, "analiza_nedostajuci_zamena.csv"), index=False, encoding="utf-8-sig")

    print("\n=== Prirodne rupe u testu ===")
    print(natural.to_string(index=False))
    print("\n=== Vestacko brisanje (redovi gde sve postoji) ===")
    print(masked.to_string(index=False))
    print("\n=== Zamena za y_lastweek ===")
    print(fallback.to_string(index=False))
    print(f"Kod prirodno nedostajuceg y_lastweek, vrednost od pre 14 dana postoji u {coverage:.1f}% redova")
    print("\n=== 14.10.2017 ===")
    print(day_rows.to_string(index=False))


# ---------------------------------------------------------------- ablacija

def part_ablation(bundle: dict, train: pd.DataFrame, test: pd.DataFrame) -> None:
    params = retrain_params(bundle)
    overall, by_horizon = [], []
    for name, removed in ABLATIONS.items():
        features = [f for f in FEATURES if f not in removed]
        print(f"  trening: {name} ({len(features)} ulaza)...")
        pred, seconds = train_and_predict(params, train, test, features)
        mae, rmse = metrics_pp(test["target"].to_numpy(), pred)
        horizon_mae = mae_by_horizon(test, pred)
        overall.append({"varijanta": name, "izbaceno": ", ".join(removed) or "-", "MAE": round(mae, 2), "RMSE": round(rmse, 2),
                        **{f"MAE_{h}min": round(horizon_mae[h], 2) for h in REPORT_HORIZONS_MIN}, "trening_s": round(seconds)})
        by_horizon += [{"varijanta": name, "horizon_minutes": h, "MAE": round(v, 3)} for h, v in horizon_mae.items()]

    overall = pd.DataFrame(overall)
    by_horizon = pd.DataFrame(by_horizon)
    overall.to_csv(os.path.join(OUTPUT_DIR, "analiza_ablacija.csv"), index=False, encoding="utf-8-sig")
    by_horizon.to_csv(os.path.join(OUTPUT_DIR, "analiza_ablacija_po_horizontu.csv"), index=False, encoding="utf-8-sig")
    print("\n=== Ablacija ===")
    print(overall.to_string(index=False))
    plot_ablation(by_horizon)


def plot_ablation(by_horizon: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for name, style in ABLATION_STYLE.items():
        s = by_horizon[by_horizon["varijanta"] == name].sort_values("horizon_minutes")
        ax.plot(s["horizon_minutes"] / 60, s["MAE"], linewidth=2, markersize=5, markevery=3, label=name, **style)
    ax.set_title("Ablacija: model ponovo treniran bez grupe ulaza", fontsize=10, color=INK, loc="left")
    ax.set_xlabel("Horizont predikcije (h)", fontsize=9, color=MUTED)
    ax.set_ylabel("MAE (procentni poeni zauzetosti)", fontsize=9, color=MUTED)
    ax.set_xticks(range(0, 17, 2))
    ax.set_ylim(bottom=0)
    _style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.05), ncol=4, frameon=False, fontsize=9)
    fig.text(0.01, 0.01, "trenutno stanje = y_t, y_t1, y_t2, delta · isti termin ranije = y_yesterday, y_lastweek",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    _save(fig, "analiza_ablacija.png")
    plt.close(fig)


# ------------------------------------------------------------------ duzina

def part_train_length(bundle: dict, train: pd.DataFrame, test: pd.DataFrame) -> None:
    params = retrain_params(bundle)
    rows = []
    for name, window in TRAIN_WINDOWS.items():
        part = train if window is None else train[train["target_time"] >= TEST_START - window]
        print(f"  trening: {name} ({len(part)} redova)...")
        pred, seconds = train_and_predict(params, part, test, FEATURES)
        mae, rmse = metrics_pp(test["target"].to_numpy(), pred)
        horizon_mae = mae_by_horizon(test, pred)
        rows.append({"trening": name, "n_train": len(part), "MAE": round(mae, 2), "RMSE": round(rmse, 2),
                     **{f"MAE_{h}min": round(horizon_mae[h], 2) for h in REPORT_HORIZONS_MIN}, "trening_s": round(seconds)})
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(OUTPUT_DIR, "analiza_duzina_treninga.csv"), index=False, encoding="utf-8-sig")
    print("\n=== Duzina trening skupa ===")
    print(table.to_string(index=False))


# -------------------------------------------------------- specijalizovani

def part_specialized(bundle: dict, train: pd.DataFrame, test: pd.DataFrame) -> None:
    params = retrain_params(bundle)
    features = [f for f in FEATURES if f != "horizon_minutes"]
    rows = []
    for minutes in SPECIALIZED_HORIZONS_MIN:
        tr = train[train["horizon_minutes"] == minutes]
        te = test[test["horizon_minutes"] == minutes]
        pred, seconds = train_and_predict(params, tr, te, features)
        rows.append(
            {
                "horizont_min": minutes,
                "MAE_specijalizovan": round(mae_pp(te["target"], pred), 2),
                "MAE_jedan_model": round(mae_pp(te["target"], predict(bundle, te)), 2),
                "n_train_specijalizovan": len(tr),
                "n_test": len(te),
                "trening_s": round(seconds),
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(OUTPUT_DIR, "analiza_specijalizovani.csv"), index=False, encoding="utf-8-sig")
    print("\n=== Jedan model naspram specijalizovanih (isti test redovi) ===")
    print(table.to_string(index=False))


# -------------------------------------------------------------------- main

PARTS = ["doprinos", "greske", "nedostajuci", "ablacija", "duzina", "specijalizovani"]


def main(parts: list[str]) -> None:
    unknown = set(parts) - set(PARTS)
    if unknown:
        raise SystemExit(f"Nepoznat deo: {', '.join(sorted(unknown))}. Moguci: {', '.join(PARTS)}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konzola: "č", "–" u tabelama

    print(f"Gradim trening/test skup ({len(HORIZON_STEPS_RANGE)} horizonata)...")
    train, test = prepare_multi_horizon_dataset(CITY, HORIZON_STEPS_RANGE)
    test["carpark"] = pd.Categorical(test["carpark"].astype(str), categories=train["carpark"].cat.categories)
    print(f"Train: {len(train)} redova, Test: {len(test)} redova")
    bundle = load_bundle()

    for part in PARTS:
        if part not in parts:
            continue
        start = time.perf_counter()
        print(f"\n##### {part} #####")
        if part == "doprinos":
            part_contributions(bundle, test)
        elif part == "greske":
            part_errors(bundle, test)
        elif part == "nedostajuci":
            part_missing(bundle, train, test)
        elif part == "ablacija":
            part_ablation(bundle, train, test)
        elif part == "duzina":
            part_train_length(bundle, train, test)
        elif part == "specijalizovani":
            part_specialized(bundle, train, test)
        print(f"({part}: {time.perf_counter() - start:.0f} s)")


if __name__ == "__main__":
    main(sys.argv[1:] or PARTS)
