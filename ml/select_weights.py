"""
Korak 6b (PLAN_ZAVRSETKA.md) - izbor pondera preporuke na VALIDACIONOM periodu.

Ponderi formule (backend/recommender.py)
    skor = w1*dostupnost + w2*blizina_cilju - w3*vreme_voznje
do koraka 6b bili su izabrani rucno. Ovde se biraju na oktobru 2017
(eval_recommender.VALIDATION_PERIOD), a konacni brojevi se mere u
ml/eval_recommender.py na novembru i decembru, sa drugim vozacima. Isti
princip kao kod modela: ono na cemu se bira ne sme da bude ono na cemu se meri.

Kombinacije: w1, w2, w3 >= 0, w1 + w2 + w3 = 1, korak 0,05 (231 kombinacija).
Bitan je samo odnos pondera (0.55/0.3/0.15 rangira isto kao 1.1/0.6/0.3), pa
uslov "zbir = 1" ne izostavlja nijednu kombinaciju.

PRAVILO IZBORA (dogovoreno i zapisano 5.11.2026, PRE gledanja rezultata):
1. Pun parking pri dolasku (>= 95%): zadrzavaju se kombinacije koje su
   najvise RISK_TOLERANCE_PP losije od najbolje. Na ~2000 voznji manje
   razlike su u granicama slucajnosti.
2. Medju njima se bira kombinacija sa najkracim prosecnim ukupnim vremenom
   od polaska do cilja (voznja + hodanje, odnosno cekanje i autobus sa P&R;
   eval_recommender.door_to_door_minutes).
Meri se XGBoost prognoza (ono sto aplikacija koristi), svi parkinzi koji se
preporucuju, sva vremena planiranja zajedno (0, 1, 2 i 4 h).

Provera pretpostavki: isto pravilo se ponavlja uz sporiji/brzi P&R autobus i
uz drugu toleranciju, da se vidi da li izbor zavisi od tih pretpostavki.

Samo informativno (ne ulazi u pravilo): za svaku kombinaciju se meri i scenario
"samo gradski parkinzi" (kolone gradski_*), kao kad filter "radius" izbaci P&R.
Uvedeno posle prvog pokusaja koraka 6b, kada se pokazalo da su ponderi, uz
relativnu normalizaciju, davali los izbor bez P&R u listi (vidi PROGRESS.md).

Bodovanje je ovde vektorizovano (numpy), da bi 231 kombinacija trajala
sekundama. Na kraju se proverava da daje ISTI izbor kao
recommender.score_candidates (funkcija koju koristi API).

Pokretanje (iz korena projekta):
    python ml/select_weights.py

Traje ~7 min (vecinu vremena odnose predikcije modela).
Rezultati: ml/output/izbor_pondera*.csv i izbor_pondera.png.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from backend import recommender  # noqa: E402
from backend.datasource import ReplaySource  # noqa: E402
from ml import eval_recommender as ev  # noqa: E402

VALIDATION_SEED = ev.SEED + 1  # drugi vozaci nego u konacnom testu
WEIGHT_STEP = 0.05
RISK_TOLERANCE_PP = 0.5
FULL_THRESHOLD = ev.FULL_THRESHOLDS[0]

# Varijante pretpostavki za proveru izbora: (naziv, cekanje autobusa u min,
# brzina autobusa u km/h, tolerancija u p.p., prag punog parkinga u pravilu).
# Prva je osnovna. Varijante sa pragom 90% i 85% su korak 6c.
ASSUMPTION_VARIANTS = [
    ("osnovno", ev.BUS_WAIT_MIN, ev.BUS_SPEED_KMH, RISK_TOLERANCE_PP, 0.95),
    ("sporiji autobus (10 min cekanja)", 10.0, ev.BUS_SPEED_KMH, RISK_TOLERANCE_PP, 0.95),
    ("jos sporiji autobus (10 min, 15 km/h)", 10.0, 15.0, RISK_TOLERANCE_PP, 0.95),
    ("brzi autobus (3 min, 25 km/h)", 3.0, 25.0, RISK_TOLERANCE_PP, 0.95),
    ("stroza tolerancija (0,25 p.p.)", ev.BUS_WAIT_MIN, ev.BUS_SPEED_KMH, 0.25, 0.95),
    ("blaza tolerancija (1 p.p.)", ev.BUS_WAIT_MIN, ev.BUS_SPEED_KMH, 1.0, 0.95),
    ("prag punog 90%", ev.BUS_WAIT_MIN, ev.BUS_SPEED_KMH, RISK_TOLERANCE_PP, 0.90),
    ("prag punog 85%", ev.BUS_WAIT_MIN, ev.BUS_SPEED_KMH, RISK_TOLERANCE_PP, 0.85),
]


def risk_column(threshold: float) -> str:
    return f"pun_{round(threshold * 100)}_pct"


def weight_grid(step: float = WEIGHT_STEP) -> np.ndarray:
    """Sve kombinacije (w1, w2, w3) >= 0 sa zbirom 1, na mrezi koraka `step`."""
    n = round(1 / step)
    return np.array(
        [(round(i * step, 2), round(j * step, 2), round((n - i - j) * step, 2))
         for i in range(n + 1) for j in range(n + 1 - i)]
    )


def choose_for_all_weights(groups: list[list[dict]], weights: np.ndarray) -> dict[str, np.ndarray]:
    """Za svaku grupu (vozac, vreme planiranja) i svaku kombinaciju pondera:
    koji kandidat bi bio izabran. Ista formula i normalizacija kao
    recommender.score_candidates. Vraca osobine izabranih kandidata kao
    matrice oblika (broj grupa, broj kombinacija)."""
    keys = ["rate_actual", "eta_minutes", "distance_to_destination_km", "p_and_r", "park_id"]
    chosen = {k: [] for k in keys + ["index"]}
    for group in groups:
        availability = np.array([1 - c["rate_model"] for c in group])
        walk = np.array([c["distance_to_destination_km"] for c in group])
        eta = np.array([c["eta_minutes"] for c in group])
        closeness = np.maximum(0.0, 1 - walk / recommender.WALK_SCALE_KM)
        drive_time = np.minimum(1.0, eta / recommender.DRIVE_SCALE_MIN)
        components = np.column_stack([availability, closeness, -drive_time])
        # score_candidates zaokruzuje skor na 4 decimale, pa i ovde (isti izbor
        # pri skoro jednakim skorovima); argmax uzima prvog, kao i stabilno sortiranje.
        scores = np.round(components @ weights.T, 4)
        best = scores.argmax(axis=0)
        chosen["index"].append(best)
        for k in keys:
            values = np.array([c[k] for c in group])
            chosen[k].append(values[best])
    return {k: np.array(v) for k, v in chosen.items()}


def door_to_door(chosen: dict[str, np.ndarray], bus_wait_min: float, bus_speed_kmh: float) -> np.ndarray:
    """Vektorizovana verzija eval_recommender.door_to_door_minutes."""
    walk = chosen["distance_to_destination_km"]
    last_leg = np.where(
        chosen["p_and_r"].astype(bool),
        bus_wait_min + walk / bus_speed_kmh * 60.0,
        walk / ev.WALK_SPEED_KMH * 60.0,
    )
    return chosen["eta_minutes"] + last_leg


def summarize_weights(chosen: dict[str, np.ndarray], weights: np.ndarray, bus_wait_min: float, bus_speed_kmh: float) -> pd.DataFrame:
    p_and_r = chosen["p_and_r"].astype(bool)
    return pd.DataFrame(
        {
            "w1": weights[:, 0],
            "w2": weights[:, 1],
            "w3": weights[:, 2],
            **{risk_column(t): 100 * (chosen["rate_actual"] >= t).mean(axis=0) for t in ev.FULL_THRESHOLDS},
            "vreme_do_cilja_min": door_to_door(chosen, bus_wait_min, bus_speed_kmh).mean(axis=0),
            "voznja_min": chosen["eta_minutes"].mean(axis=0),
            "do_cilja_km": chosen["distance_to_destination_km"].mean(axis=0),
            "p_and_r_pct": 100 * p_and_r.mean(axis=0),
        }
    )


def apply_rule(table: pd.DataFrame, tolerance_pp: float, threshold: float = FULL_THRESHOLD) -> pd.Series:
    """Pravilo izbora iz docstringa (prag punog parkinga je parametar samo
    radi provere osetljivosti; glavni izbor koristi 95%)."""
    risk = risk_column(threshold)
    best_risk = table[risk].min()
    eligible = table[table[risk] <= best_risk + tolerance_pp]
    return eligible.sort_values(["vreme_do_cilja_min", risk]).iloc[0]


def pareto_front(table: pd.DataFrame) -> pd.DataFrame:
    """Kombinacije koje nijedna druga ne nadmasuje u oba merila (krace vreme
    I manje punih parkinga)."""
    front = []
    best_risk = np.inf
    for _, row in table.sort_values(["vreme_do_cilja_min", "pun_95_pct"]).iterrows():
        if row["pun_95_pct"] < best_risk:
            front.append(row)
            best_risk = row["pun_95_pct"]
    return pd.DataFrame(front)


def check_against_api_scoring(groups: list[list[dict]], chosen: dict[str, np.ndarray], weights: np.ndarray, which: list[int]) -> None:
    """Vektorizovani izbor mora da bude isti kao recommender.score_candidates."""
    for k in which:
        w = tuple(float(x) for x in weights[k])
        same = 0
        for g, group in enumerate(groups):
            candidates = [
                {"index": i, "availability_score": 1 - c["rate_model"],
                 "distance_to_destination_km": c["distance_to_destination_km"], "eta_minutes": c["eta_minutes"]}
                for i, c in enumerate(group)
            ]
            same += recommender.score_candidates(candidates, w)[0]["index"] == chosen["index"][g, k]
        print(f"  provera {w}: isti izbor kao score_candidates u {same}/{len(groups)} slucajeva")


def label(row: pd.Series) -> str:
    return f"{row['w1']:.2f} / {row['w2']:.2f} / {row['w3']:.2f}"


def plot_pareto(table: pd.DataFrame, front: pd.DataFrame, chosen_row: pd.Series, hand_row: pd.Series) -> None:
    """Sve kombinacije: pun parking naspram vremena do cilja, uz Pareto front,
    izabranu i rucno izabranu kombinaciju."""
    import matplotlib.pyplot as plt

    blue, orange, gray = ev.PLOT_STYLE["model"]["color"], ev.PLOT_STYLE["naivna"]["color"], ev.PLOT_STYLE["najblizi"]["color"]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(table["vreme_do_cilja_min"], table["pun_95_pct"], s=14, color=gray, alpha=0.45,
               linewidths=0, label=f"sve kombinacije ({len(table)})")
    ax.plot(front["vreme_do_cilja_min"], front["pun_95_pct"], color=blue, linewidth=2, marker="o",
            markersize=4, label="Pareto front (nijedna druga nije bolja u oba merila)")
    limit = table["pun_95_pct"].min() + RISK_TOLERANCE_PP
    ax.axhline(limit, color=ev.MUTED, linewidth=1, linestyle=":")
    ax.annotate(f"dozvoljeno: najbolja + {RISK_TOLERANCE_PP:g} p.p.", (table["vreme_do_cilja_min"].max(), limit),
                xytext=(0, 4), textcoords="offset points", ha="right", fontsize=8, color=ev.MUTED)
    ax.scatter([hand_row["vreme_do_cilja_min"]], [hand_row["pun_95_pct"]], s=70, marker="s", color=orange,
               edgecolors="white", linewidths=1.5, zorder=5, label=f"ručno izabrano ({label(hand_row)})")
    ax.scatter([chosen_row["vreme_do_cilja_min"]], [chosen_row["pun_95_pct"]], s=110, marker="D", color=blue,
               edgecolors="white", linewidths=1.5, zorder=6, label=f"izabrano pravilom ({label(chosen_row)})")
    ax.set_xlabel("Prosečno vreme od polaska do cilja (min)", fontsize=9, color=ev.MUTED)
    ax.set_ylabel("Dolazak na pun parking (≥95%), % vožnji", fontsize=9, color=ev.MUTED)
    ax.set_title("Izbor pondera w1/w2/w3 · validacioni period (oktobar 2017)", fontsize=10, color=ev.INK, loc="left")
    ev._style_axes(ax)
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    fig.tight_layout()
    ev._save(fig, "izbor_pondera.png")
    plt.close(fig)


def main() -> None:
    os.makedirs(ev.OUTPUT_DIR, exist_ok=True)
    print("Ucitavam podatke i model...")
    source = ReplaySource(city=ev.CITY)
    parks = ev.recommendable_parks()
    trips = ev.generate_trips(np.random.default_rng(VALIDATION_SEED), ev.VALIDATION_PERIOD)
    start, end = ev.VALIDATION_PERIOD
    print(f"{len(trips)} vozaca u validacionom periodu {start.date()} - {end.date()} (bez kraja), {len(parks)} parkinga")

    print("Racunam dolaske i predikcije...")
    options = ev.build_options(trips, source, parks)
    groups = ev.group_options(options)
    weights = weight_grid()
    print(f"{len(groups)} odluka x {len(weights)} kombinacija pondera")
    chosen = choose_for_all_weights(groups, weights)
    city_groups = ev.group_options(options[options["city_park"]])
    chosen_city = choose_for_all_weights(city_groups, weights)

    # Osnovna varijanta: sve kombinacije, Pareto front, izbor po pravilu.
    _, bus_wait, bus_speed, tolerance, _ = ASSUMPTION_VARIANTS[0]
    table = summarize_weights(chosen, weights, bus_wait, bus_speed)
    city_table = summarize_weights(chosen_city, weights, bus_wait, bus_speed)
    for col in ["pun_95_pct", "pun_90_pct", "vreme_do_cilja_min", "do_cilja_km"]:
        table[f"gradski_{col}"] = city_table[col]
    front = pareto_front(table)
    chosen_row = apply_rule(table, tolerance)
    hand_mask = np.all(np.isclose(weights, ev.HAND_PICKED_WEIGHTS), axis=1)
    hand_row = table[hand_mask].iloc[0]
    table.round(3).to_csv(os.path.join(ev.OUTPUT_DIR, "izbor_pondera.csv"), index=False)
    front.round(3).to_csv(os.path.join(ev.OUTPUT_DIR, "izbor_pondera_pareto.csv"), index=False)

    # Provera pretpostavki: da li se izbor menja?
    variant_rows = []
    for name, wait, speed, tol, threshold in ASSUMPTION_VARIANTS:
        variant_table = summarize_weights(chosen, weights, wait, speed)
        row = apply_rule(variant_table, tol, threshold)
        variant_rows.append({
            "varijanta": name, "cekanje_min": wait, "autobus_kmh": speed, "tolerancija_pp": tol,
            "prag_pct": round(threshold * 100), **row.to_dict(),
        })
    variants = pd.DataFrame(variant_rows)
    variants.round(3).to_csv(os.path.join(ev.OUTPUT_DIR, "izbor_pondera_provera.csv"), index=False)

    pd.set_option("display.width", 200)
    cols = ["w1", "w2", "w3", "pun_95_pct", "pun_90_pct", "pun_85_pct", "vreme_do_cilja_min", "voznja_min", "do_cilja_km", "p_and_r_pct"]
    print(f"\nNajbolji rizik: {table['pun_95_pct'].min():.2f}%  ->  dozvoljeno do {table['pun_95_pct'].min() + tolerance:.2f}%")
    city_cols = ["gradski_pun_95_pct", "gradski_vreme_do_cilja_min", "gradski_do_cilja_km"]
    print("\n=== Izabrano pravilom ===")
    print(chosen_row[cols + city_cols].round(3).to_string())
    print("\n=== Rucno izabrano (0.55/0.3/0.15) ===")
    print(hand_row[cols + city_cols].round(3).to_string())
    print("\n=== Pareto front ===")
    print(front[cols].round(2).to_string(index=False))
    print("\n=== 10 najbrzih dozvoljenih kombinacija ===")
    eligible = table[table["pun_95_pct"] <= table["pun_95_pct"].min() + tolerance]
    print(eligible.sort_values("vreme_do_cilja_min")[cols + city_cols].head(10).round(2).to_string(index=False))
    print("\n=== Provera pretpostavki ===")
    print(variants[["varijanta"] + cols].round(2).to_string(index=False))

    print("\nProvera vektorizovanog bodovanja:")
    chosen_k = int(np.flatnonzero(np.all(np.isclose(weights, chosen_row[["w1", "w2", "w3"]].to_numpy(float)), axis=1))[0])
    check_against_api_scoring(groups, chosen, weights, [chosen_k, int(np.flatnonzero(hand_mask)[0])])

    plot_pareto(table, front, chosen_row, hand_row)


if __name__ == "__main__":
    main()
