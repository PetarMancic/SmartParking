"""
Korak 7 (PLAN_ZAVRSETKA.md; MASTER_PLAN.md, poglavlje 8) - da li model
predikcije radi i u drugim gradovima, i koliko rezultati zavise od Norwicha.

Proverava se samo MODEL PREDIKCIJE. Preporuka se ne proverava, jer za
parkinge u drugim gradovima nemamo koordinate.

1. Isti postupak u svakom gradu ("sopstveni model"): isti ulazi, isti
   hiperparametri (iz sacuvanog Norfolk modela, bez podesavanja po gradu) i
   hronoloska podela (test = poslednja ~2 meseca, CITY_CONFIGS u data_prep.py).
   Apsolutni MAE zavisi od toga koliko se zauzetost u gradu menja, pa se model
   poredi i sa jednostavnim pravilima iz koraka 4 (pre nedelju dana, tipicna
   kriva) u istom gradu.
2. Prenos: model treniran SAMO na Norfolku primenjuje se na drugi grad bez
   ponovnog treniranja. Sifre parkinga u drugom gradu su nepoznate, pa je taj
   model bez identiteta parkinga (carpark, capacity), kao u ablaciji iz koraka
   5. Poredi se sa modelom tog grada sa istim ulazima, pa je jedina razlika na
   cijim podacima je treniran. Norfolk model za grad X trenira se samo na
   Norfolk podacima PRE test perioda grada X, da ni preko drugog grada ne vidi
   isti kalendarski period (vreme, praznici).
3. Performanse: vreme treninga po gradu i vreme predikcije jednog "ticka"
   za 15, 30 i 63 parkinga (koliko ih ima u sva cetiri grada zajedno).

Isti zadatak svuda: predvidja se zauzetost za ciljno vreme 08-23 h (dnevni
opseg merenja u Norfolku). Nocna merenja (Glasgow, Nottingham) mogu da budu
ulaz, ali se ne predvidjaju. Birmingham meri samo ~08-16:30, pa ima manje
dugih horizonata.

Ciscenje kopiranih dana (dodato posle prvog pokretanja, vidi PROGRESS.md,
korak 7): u Nottinghamu je za vise parkinga broj zauzetih mesta u 85-100%
termina TACNO isti kao pre 7 dana, sto nije stvarno merenje nego kopija
prethodne nedelje (verovatno popunjavanje rupa kod izvora). Zato se dan
parkinga u kome je bar COPY_SHARE termina (08-23 h) tacna kopija istog termina
pre 7 dana tretira kao nedostajuci podatak - ne ulazi ni u trening, ni u test,
ni kao ulaz. Dani kada se broj zauzetih mesta skoro ne menja (npr. P&R nedeljom,
0 ceo dan) ne racunaju se kao kopija. Isto pravilo vazi za sva cetiri grada.
Aplikacija i njen Norfolk model ne koriste ovo ciscenje.

Pokretanje (iz korena projekta):
    python ml/other_cities.py

Traje ~20 min (10 treniranja). Rezultati: ml/output/gradovi_*.csv i *.png.
"""

from __future__ import annotations

import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from ml.compare_models import baseline_last_week, baseline_typical, metrics_pp  # noqa: E402
from ml.data_prep import (  # noqa: E402
    CITY_CONFIGS,
    FEATURES,
    HORIZON_STEPS_RANGE,
    build_grid,
    build_horizon_frame,
    load_raw,
    resample_per_park,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_norfolk.joblib")
TRAIN_N_JOBS = 8

CITIES = ["norfolk", "birmingham", "glasgow", "nottingham"]
CITY_NAMES = {"norfolk": "Norfolk (Norwich)", "birmingham": "Birmingham", "glasgow": "Glasgow", "nottingham": "Nottingham"}
TARGET_HOURS = (8.0, 23.0)  # ciljno vreme, ukljucivo
IDENTITY = ["carpark", "capacity"]
FEATURES_NO_ID = [f for f in FEATURES if f not in IDENTITY]
REPORT_HORIZONS_MIN = [30, 120, 240, 480]
MIN_ROWS_PER_HORIZON = 500  # na grafiku: horizonti sa premalo test redova se ne crtaju
TICK_PARKS = [15, 30, 63]
TICK_REPEATS = 200
COPY_SHARE = 0.9  # dan je "kopija" ako je bar 90% termina isto kao pre 7 dana
MIN_DAILY_CHANGE = 3  # dan sa manjom promenom broja vozila (min-max) ne racuna se kao kopija
MIN_COMPARED_SLOTS = 10


def copied_days(df: pd.DataFrame) -> dict[str, pd.DatetimeIndex]:
    """Za svaki parking: dani (08-23 h) u kojima je broj zauzetih mesta u bar
    COPY_SHARE termina tacno isti kao u istom terminu pre 7 dana."""
    result = {}
    for park_id, g in df.groupby("SystemCodeNumber"):
        counts = g.set_index("LastUpdated")["Occupancy"].resample("30min").last()
        week_ago = counts.shift(7 * 48)
        day_slots = (counts.index.hour >= 8) & (counts.index.hour < 23)
        frame = pd.DataFrame({"same": counts == week_ago, "compared": counts.notna() & week_ago.notna(),
                              "count": counts})[day_slots]
        frame = frame[frame["compared"]]
        daily = frame.groupby(frame.index.normalize()).agg(
            share=("same", "mean"), slots=("same", "size"), change=("count", lambda s: s.max() - s.min()))
        mask = (daily["share"] >= COPY_SHARE) & (daily["slots"] >= MIN_COMPARED_SLOTS) & (daily["change"] >= MIN_DAILY_CHANGE)
        result[park_id] = daily.index[mask]
    return result


def drop_copied_days(series: dict[str, pd.Series], copied: dict[str, pd.DatetimeIndex]) -> dict[str, pd.Series]:
    """Kopirani dani postaju NaN (ceo dan), kao i svaki drugi nedostajuci podatak."""
    return {park_id: s.where(~s.index.normalize().isin(copied.get(park_id, []))) for park_id, s in series.items()}


def city_rows(city: str) -> tuple[pd.DataFrame, int, dict]:
    """Sve (parking, trenutak, horizont) kombinacije za grad, sa ciljnim
    vremenom 08-23 h. Podela na trening i test radi se kasnije, po datumu."""
    df = load_raw(city)
    capacities = df.groupby("SystemCodeNumber")["Capacity"].first()
    series = resample_per_park(df)
    copied = copied_days(df)
    series = drop_copied_days(series, copied)
    park_days = sum(s.dropna().index.normalize().nunique() for s in resample_per_park(df).values())
    cleaning = {
        "kopiranih_dana": int(sum(len(v) for v in copied.values())),
        "dana_parkinga": int(park_days),
        "po_parkingu": {p: len(v) for p, v in copied.items() if len(v)},
    }
    grid = build_grid(series)
    frames = []
    for horizon_steps in HORIZON_STEPS_RANGE:
        d = build_horizon_frame(series, grid, capacities, horizon_steps)
        frames.append(d[d["hour"].between(*TARGET_HOURS)])
    rows = pd.concat(frames, ignore_index=True)
    # Iste kategorije u treningu i testu (XGBoost koristi kodove kategorija).
    rows["carpark"] = pd.Categorical(rows["carpark"].astype(str), categories=sorted(series))
    float_cols = rows.select_dtypes("float64").columns
    rows[float_cols] = rows[float_cols].astype("float32")
    return rows, len(series), cleaning


def split(rows: pd.DataFrame, city: str, train_cutoff: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = CITY_CONFIGS[city]
    cutoff = train_cutoff if train_cutoff is not None else config["test_start"]
    train = rows[rows["target_time"] < cutoff]
    test = rows[(rows["target_time"] >= config["test_start"]) & (rows["target_time"] < config["test_end"])]
    return train, test


def train_model(params: dict, train: pd.DataFrame, features: list[str]) -> tuple[xgb.XGBRegressor, float]:
    model = xgb.XGBRegressor(**params)
    start = time.perf_counter()
    model.fit(train[features], train["target"])
    return model, time.perf_counter() - start


def mae_report(test: pd.DataFrame, pred: np.ndarray, prefix: str) -> dict:
    """Ukupan MAE i MAE na izabranim horizontima, u p.p."""
    y = test["target"].to_numpy()
    out = {f"{prefix}_mae": metrics_pp(y, pred)[0]}
    for h in REPORT_HORIZONS_MIN:
        mask = (test["horizon_minutes"] == h).to_numpy()
        out[f"{prefix}_mae_{h}min"] = metrics_pp(y[mask], pred[mask])[0] if mask.any() else np.nan
    return out


def per_horizon(test: pd.DataFrame, pred: np.ndarray, city: str, variant: str) -> pd.DataFrame:
    frame = pd.DataFrame({"horizon_minutes": test["horizon_minutes"].to_numpy(),
                          "ae": np.abs(np.clip(pred, 0, 1) - test["target"].to_numpy()) * 100})
    table = frame.groupby("horizon_minutes")["ae"].agg(mae="mean", n="size").reset_index()
    table.insert(0, "varijanta", variant)
    table.insert(0, "grad", city)
    return table


def tick_timing(model: xgb.XGBRegressor, rows: pd.DataFrame) -> list[dict]:
    """Vreme predikcije jednog "ticka": po jedan red za N parkinga (jedan
    horizont, kao boje markera na mapi) i N x 31 red (svi horizonti)."""
    results = []
    for n in TICK_PARKS:
        for label, horizons in (("1 horizont", 1), ("31 horizont", len(HORIZON_STEPS_RANGE))):
            batch = rows.sample(n * horizons, replace=True, random_state=0)[FEATURES_NO_ID]
            model.predict(batch)  # zagrevanje
            times = []
            for _ in range(TICK_REPEATS):
                start = time.perf_counter()
                model.predict(batch)
                times.append(time.perf_counter() - start)
            results.append({"parkinga": n, "zahtev": label, "redova": n * horizons,
                            "ms_medijana": 1000 * float(np.median(times))})
    return results


# -------------------------------------------------------------------- grafici

# Validirana kategorijska paleta iz koraka 4 (dataviz, --pairs all: PASS).
# Identitet nikad samo bojom: legenda + oblik markera.
CITY_STYLE = {
    "norfolk": {"color": "#2a78d6", "marker": "o"},
    "birmingham": {"color": "#eda100", "marker": "s"},
    "glasgow": {"color": "#1baf7a", "marker": "D"},
    "nottingham": {"color": "#e87ba4", "marker": "v"},
}
VARIANT_STYLE = {
    "sopstveni": {"color": "#2a78d6", "label": "sopstveni model grada"},
    "sopstveni_bez_id": {"color": "#1baf7a", "label": "sopstveni, bez identiteta parkinga"},
    "prenos_norfolk": {"color": "#eda100", "label": "Norfolk model, bez ponovnog treninga"},
    "pre_nedelju": {"color": "#898781", "label": "pravilo: pre nedelju dana"},
}
INK, MUTED, GRID = "#21201c", "#52514e", "#e4e3dc"


def _style_axes(ax) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)


def plot_by_horizon(horizons: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    data = horizons[(horizons["varijanta"] == "sopstveni") & (horizons["n"] >= MIN_ROWS_PER_HORIZON)]
    for city in CITIES:
        s = data[data["grad"] == city]
        style = CITY_STYLE[city]
        ax.plot(s["horizon_minutes"] / 60, s["mae"], color=style["color"], marker=style["marker"],
                markersize=4, linewidth=2, label=CITY_NAMES[city])
    ax.set_xlabel("Horizont prognoze (h)", fontsize=9, color=MUTED)
    ax.set_ylabel("MAE (p.p. zauzetosti)", fontsize=9, color=MUTED)
    ax.set_title("Isti model, sopstveni podaci svakog grada · ciljno vreme 08–23 h", fontsize=10, color=INK, loc="left")
    ax.set_ylim(bottom=0)
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "gradovi_po_horizontu.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Sacuvan grafik: {path}")


def plot_transfer(summary: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    columns = {"sopstveni": "sopstveni_mae", "sopstveni_bez_id": "sopstveni_bez_id_mae",
               "prenos_norfolk": "prenos_norfolk_mae", "pre_nedelju": "pre_nedelju_mae"}
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.2
    x = np.arange(len(summary))
    for i, (variant, column) in enumerate(columns.items()):
        values = summary[column].to_numpy(dtype=float)
        style = VARIANT_STYLE[variant]
        bars = ax.bar(x + (i - 1.5) * width, np.nan_to_num(values), width * 0.92, color=style["color"],
                      label=style["label"], edgecolor="white", linewidth=1)
        for bar, value in zip(bars, values):
            if not np.isnan(value):
                ax.annotate(f"{value:.1f}", (bar.get_x() + bar.get_width() / 2, value), xytext=(0, 2),
                            textcoords="offset points", ha="center", fontsize=7, color=INK)
    ax.set_xticks(x, [CITY_NAMES[c] for c in summary["grad"]])
    ax.set_ylabel("MAE (p.p. zauzetosti), svi horizonti", fontsize=9, color=MUTED)
    ax.set_title("Prenos Norfolk modela na druge gradove · ciljno vreme 08–23 h", fontsize=10, color=INK, loc="left")
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "gradovi_prenos.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Sacuvan grafik: {path}")


# ----------------------------------------------------------------------- main

def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    params = joblib.load(MODEL_PATH)["model"].get_params()
    params["n_jobs"] = TRAIN_N_JOBS

    print("Pripremam podatke za sve gradove...")
    rows, n_parks, cleaning = {}, {}, {}
    for city in CITIES:
        rows[city], n_parks[city], cleaning[city] = city_rows(city)
        c = cleaning[city]
        print(f"  {city}: {n_parks[city]} parkinga, {len(rows[city])} redova; uklonjeno kopiranih dana "
              f"{c['kopiranih_dana']} od {c['dana_parkinga']} ({100 * c['kopiranih_dana'] / c['dana_parkinga']:.1f}%) "
              f"{c['po_parkingu']}")

    summary_rows, horizon_tables, timing_rows = [], [], []
    norfolk_transfer_models: dict[pd.Timestamp, xgb.XGBRegressor] = {}
    for city in CITIES:
        config = CITY_CONFIGS[city]
        train, test = split(rows[city], city)
        print(f"\n=== {city}: trening {len(train)} redova (do {config['test_start'].date()}), test {len(test)} redova")
        y = test["target"].to_numpy()
        row = {
            "grad": city, "parkinga": n_parks[city],
            "trening_od": rows[city]["target_time"].min().date(), "test_od": config["test_start"].date(),
            "test_do": (config["test_end"] - pd.Timedelta(days=1)).date(),
            "trening_redova": len(train), "test_redova": len(test),
            "kopiranih_dana_uklonjeno": cleaning[city]["kopiranih_dana"],
            "kopiranih_dana_pct": 100 * cleaning[city]["kopiranih_dana"] / cleaning[city]["dana_parkinga"],
            "prosecna_zauzetost_test_pct": 100 * float(y.mean()),
        }

        model, seconds = train_model(params, train, FEATURES)
        pred = np.clip(model.predict(test[FEATURES]), 0, 1)
        row.update(mae_report(test, pred, "sopstveni"))
        row["sopstveni_rmse"] = metrics_pp(y, pred)[1]
        row["trening_s"] = seconds
        horizon_tables.append(per_horizon(test, pred, city, "sopstveni"))

        for name, baseline in (("pre_nedelju", baseline_last_week), ("tipicna_kriva", baseline_typical)):
            row.update(mae_report(test, baseline(train, test), name))
        horizon_tables.append(per_horizon(test, baseline_last_week(train, test), city, "pre_nedelju"))

        model_no_id, _ = train_model(params, train, FEATURES_NO_ID)
        pred_no_id = np.clip(model_no_id.predict(test[FEATURES_NO_ID]), 0, 1)
        row.update(mae_report(test, pred_no_id, "sopstveni_bez_id"))
        horizon_tables.append(per_horizon(test, pred_no_id, city, "sopstveni_bez_id"))

        if city == "norfolk":
            # Isti model sluzi za prenos u grad sa istim pocetkom testa (Nottingham).
            norfolk_transfer_models[config["test_start"]] = model_no_id
        else:
            cutoff = config["test_start"]
            if cutoff not in norfolk_transfer_models:
                norfolk_train, _ = split(rows["norfolk"], "norfolk", train_cutoff=cutoff)
                print(f"  Norfolk model bez identiteta, trening do {cutoff.date()} ({len(norfolk_train)} redova)")
                norfolk_transfer_models[cutoff], _ = train_model(params, norfolk_train, FEATURES_NO_ID)
            pred_transfer = np.clip(norfolk_transfer_models[cutoff].predict(test[FEATURES_NO_ID]), 0, 1)
            row.update(mae_report(test, pred_transfer, "prenos_norfolk"))
            horizon_tables.append(per_horizon(test, pred_transfer, city, "prenos_norfolk"))
        summary_rows.append(row)
        print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()})

    summary = pd.DataFrame(summary_rows)
    best_baseline = summary[["pre_nedelju_mae", "tipicna_kriva_mae"]].min(axis=1)
    summary["bolji_od_najboljeg_pravila_pct"] = 100 * (1 - summary["sopstveni_mae"] / best_baseline)
    horizons = pd.concat(horizon_tables, ignore_index=True)

    # Performanse: Norfolk model bez identiteta (istog oblika kao model u aplikaciji)
    # na redovima iz sva cetiri grada.
    all_rows = pd.concat([split(rows[c], c)[1] for c in CITIES], ignore_index=True)
    timing_rows = tick_timing(norfolk_transfer_models[CITY_CONFIGS["nottingham"]["test_start"]], all_rows)
    timing = pd.DataFrame(timing_rows)

    summary.round(3).to_csv(os.path.join(OUTPUT_DIR, "gradovi_tacnost.csv"), index=False)
    horizons.round(3).to_csv(os.path.join(OUTPUT_DIR, "gradovi_po_horizontu.csv"), index=False)
    timing.round(3).to_csv(os.path.join(OUTPUT_DIR, "gradovi_performanse.csv"), index=False)

    pd.set_option("display.width", 220)
    print("\n=== Tacnost po gradu (MAE, p.p.) ===")
    cols = ["grad", "parkinga", "prosecna_zauzetost_test_pct", "sopstveni_mae", "sopstveni_mae_30min",
            "sopstveni_mae_120min", "sopstveni_mae_240min", "sopstveni_mae_480min", "pre_nedelju_mae",
            "tipicna_kriva_mae", "bolji_od_najboljeg_pravila_pct", "trening_s"]
    print(summary[cols].round(2).to_string(index=False))
    print("\n=== Prenos (MAE, p.p.) ===")
    cols = ["grad", "sopstveni_mae", "sopstveni_bez_id_mae", "prenos_norfolk_mae", "pre_nedelju_mae",
            "sopstveni_bez_id_mae_30min", "prenos_norfolk_mae_30min", "sopstveni_bez_id_mae_240min", "prenos_norfolk_mae_240min"]
    print(summary[cols].round(2).to_string(index=False))
    print("\n=== Vreme predikcije jednog ticka ===")
    print(timing.round(3).to_string(index=False))

    plot_by_horizon(horizons)
    plot_transfer(summary)


if __name__ == "__main__":
    main()
