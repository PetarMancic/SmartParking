"""
Korak 3 (PLAN_ZAVRSETKA.md) - evaluacija PREPORUKE simulacijom vozaca nad
test periodom (1.10.-5.12.2017, podaci koje model nije video pri treningu).

Pitanje: da li preporuka zaista pomaze vozacu - koliko cesto stigne na pun
parking i koliko mora da hoda, u poredjenju sa jednostavnim strategijama?

Postupak:
1. Generise se N_TRIPS vozaca: nasumican trenutak u test periodu (pon-sub,
   08:00-19:30), polazak na 3-8 km od centra Norwicha, destinacija u krugu od
   1,2 km oko centra. Svaki vozac se posmatra za vise "vremena planiranja"
   (LEAD_TIMES_MIN): 0 = krece odmah, 60 = planira sat unapred, itd.
2. Za svaki parking se racuna dolazak isto kao u backend/recommender.py
   (prava linija, 30 km/h, zaokruzeno na 30-min mrezu).
3. Strategije biraju jedan parking; ishod se meri na STVARNOJ zauzetosti u
   trenutku dolaska:
     - najblizi:  najblizi parking destinaciji (vozac bez sistema)
     - nasumicno: nasumican parking (donja granica)
     - naivna:    nasa formula, ali prognoza = "ostaje kao sada"
     - model:     nasa formula sa XGBoost prognozom (ono sto API radi)
     - oracle:    nasa formula sa savrsenom prognozom (gornja granica)
   naivna/model/oracle koriste ISTU funkciju bodovanja kao API
   (recommender.score_candidates) - razlikuju se samo u prognozi.
4. Analiza osetljivosti pondera: w1 (dostupnost) od 0 do 1, w2 = 1 - w1,
   w3 (saobracaj) = 0.

Ogranicenja (upisati u rad):
- Nedelja je izostavljena: P&R parkinzi nedeljom ne rade, pa im je zauzetost 0
  i izgledaju "slobodno".
- Kandidati su 14 parkinga (8 gradskih + 6 Park & Ride, koordinate iz
  zvanicnog NCC feeda); B&Q Boundary Road (parking prodavnice) se ne
  preporucuje (recommender.RECOMMENDABLE_TYPES). Do 2026-10-28 kandidata je
  bilo 9, sa koordinatama iz postanskog broja - vidi PROGRESS.md.
- Kandidat mora imati ocitavanje u trenutku "sada" (inace backend nema
  predikciju) i u trenutku dolaska (inace ishod ne moze da se izmeri).
- "Hodanje" do P&R parkinga je ~4-5 km - u stvarnosti se ide autobusom. Zato
  postoji i scenario "samo gradski parkinzi".

Pokretanje (iz korena projekta):
    python ml/eval_recommender.py

Traje ~7 min (vecinu vremena odnosi ~72 hiljade predikcija modela).
Rezultati: ml/output/eval_recommender_*.csv i *.png.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import parks as parks_module  # noqa: E402
from backend import predictor, recommender  # noqa: E402
from backend.datasource import ReplaySource  # noqa: E402
from ml.data_prep import CITY_CONFIGS  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

CITY = "norfolk"
CITY_CENTER = (52.6286, 1.2924)  # centar Norwicha (okolina The Forum / pijace)
N_TRIPS = 2000
SEED = 42
ORIGIN_DISTANCE_KM = (3.0, 8.0)
DESTINATION_RADIUS_KM = 1.2
FIRST_SLOT, LAST_SLOT = "08:00", "19:30"
LEAD_TIMES_MIN = [0, 60, 120, 240]
FULL_THRESHOLDS = (0.95, 0.90)
WEIGHT_SWEEP_W1 = [round(w, 1) for w in np.arange(0.0, 1.01, 0.1)]
SWEEP_LEAD_TIMES_MIN = [0, 120]

DEFAULT_WEIGHTS = (
    recommender.W1_PREDICTED_AVAILABILITY,
    recommender.W2_PROXIMITY,
    recommender.W3_TRAFFIC,
)
STRATEGIES = ["najblizi", "nasumicno", "naivna", "model", "oracle"]
# Koja prognoza zauzetosti ulazi u formulu za svaku "pametnu" strategiju.
FORECAST_KEY = {"naivna": "rate_now", "model": "rate_model", "oracle": "rate_actual"}


def _point_at(center: tuple[float, float], distance_km: float, bearing_rad: float) -> tuple[float, float]:
    lat = center[0] + (distance_km / 111.32) * math.cos(bearing_rad)
    lng = center[1] + (distance_km / (111.32 * math.cos(math.radians(center[0])))) * math.sin(bearing_rad)
    return lat, lng


def generate_trips(rng: np.random.Generator) -> pd.DataFrame:
    test_start = CITY_CONFIGS[CITY]["test_start"]
    test_end = CITY_CONFIGS[CITY]["test_end"]
    days = [d for d in pd.date_range(test_start, test_end, freq="D", inclusive="left") if d.dayofweek < 6]
    slots = pd.timedelta_range(FIRST_SLOT + ":00", LAST_SLOT + ":00", freq="30min")

    trips = []
    for trip_id in range(N_TRIPS):
        now = days[rng.integers(len(days))] + slots[rng.integers(len(slots))]
        origin = _point_at(CITY_CENTER, rng.uniform(*ORIGIN_DISTANCE_KM), rng.uniform(0, 2 * math.pi))
        # sqrt(u) - ravnomerno po povrsini kruga, ne zgusnuto u centru
        destination = _point_at(
            CITY_CENTER, DESTINATION_RADIUS_KM * math.sqrt(rng.uniform()), rng.uniform(0, 2 * math.pi)
        )
        trips.append(
            {
                "trip_id": trip_id,
                "now": now,
                "origin_lat": origin[0],
                "origin_lng": origin[1],
                "dest_lat": destination[0],
                "dest_lng": destination[1],
            }
        )
    return pd.DataFrame(trips)


def build_options(trips: pd.DataFrame, source: ReplaySource, parks: list[dict]) -> pd.DataFrame:
    """Jedan red = (vozac, vreme planiranja, parking): udaljenosti, horizont,
    trenutna / predvidjena / stvarna zauzetost u trenutku dolaska."""
    categories = predictor.carpark_categories()
    rows = []
    for park in parks:
        history = source.history_until(park["park_id"], source.grid_bounds()[1])
        park_rows = []
        for trip in trips.itertuples():
            d_origin = recommender._haversine_km(trip.origin_lat, trip.origin_lng, park["lat"], park["lng"])
            d_dest = recommender._haversine_km(trip.dest_lat, trip.dest_lng, park["lat"], park["lng"])
            eta_minutes = d_origin / recommender.ASSUMED_DRIVE_SPEED_KMH * 60.0
            for lead in LEAD_TIMES_MIN:
                arrival = trip.now + pd.Timedelta(minutes=lead + eta_minutes)
                steps = recommender._horizon_steps_for_arrival(trip.now, arrival)
                target = trip.now + pd.Timedelta(minutes=30 * steps)
                park_rows.append(
                    {
                        "trip_id": trip.trip_id,
                        "lead_min": lead,
                        "now": trip.now,
                        "park_id": park["park_id"],
                        "city_park": park["type"] == "grad",
                        "p_and_r": park["type"] == "Park & Ride",
                        "distance_to_origin_km": d_origin,
                        "distance_to_destination_km": d_dest,
                        "horizon_steps": steps,
                        "rate_now": history.get(trip.now, np.nan),
                        "rate_actual": history.get(target, np.nan),
                    }
                )
        predictions = predictor.predict_rates(
            history,
            [(r["now"], r["horizon_steps"]) for r in park_rows],
            park["park_id"],
            park["capacity"],
            categories,
        )
        for row, prediction in zip(park_rows, predictions):
            row["rate_model"] = np.nan if prediction is None else prediction
        rows.extend(park_rows)
        print(f"  {park['park_id']}: {len(park_rows)} kombinacija")

    options = pd.DataFrame(rows)
    # Kandidat mora imati ocitavanje sada (inace backend nema predikciju) i u
    # trenutku dolaska (inace ishod ne moze da se izmeri).
    return options.dropna(subset=["rate_now", "rate_actual", "rate_model"])


def group_options(options: pd.DataFrame) -> list[list[dict]]:
    """Kandidati grupisani po (vozac, vreme planiranja) - liste recnika, da
    simulacija ne bi isla kroz pandas za svaku od ~100 hiljada odluka."""
    groups = []
    for _, group in options.groupby(["trip_id", "lead_min"], sort=False):
        if len(group) >= 2:  # sa jednim kandidatom nema izbora - nije informativno
            groups.append(group.to_dict("records"))
    return groups


def choose(group: list[dict], strategy: str, weights, rng: np.random.Generator) -> dict:
    if strategy == "najblizi":
        return min(group, key=lambda c: c["distance_to_destination_km"])
    if strategy == "nasumicno":
        return group[rng.integers(len(group))]

    forecast_key = FORECAST_KEY[strategy]
    candidates = [
        {
            "option": c,
            "availability_score": 1 - c[forecast_key],
            "distance_to_destination_km": c["distance_to_destination_km"],
        }
        for c in group
    ]
    best = recommender.score_candidates(candidates, group[0]["now"].hour, weights)[0]
    return best["option"]


def simulate(groups: list[list[dict]], strategies: list[str], weights, seed: int) -> pd.DataFrame:
    """Za svaku (vozac, vreme planiranja) kombinaciju i strategiju - izabran
    parking i ishod na stvarnoj zauzetosti."""
    rng = np.random.default_rng(seed)
    outcomes = []
    for group in groups:
        for strategy in strategies:
            chosen = choose(group, strategy, weights, rng)
            outcomes.append(
                {
                    "trip_id": chosen["trip_id"],
                    "lead_min": chosen["lead_min"],
                    "strategy": strategy,
                    "now": chosen["now"],
                    "park_id": chosen["park_id"],
                    "city_park": chosen["city_park"],
                    "p_and_r": chosen["p_and_r"],
                    "walk_km": chosen["distance_to_destination_km"],
                    "drive_km": chosen["distance_to_origin_km"],
                    "actual_rate": chosen["rate_actual"],
                }
            )
    return pd.DataFrame(outcomes)


def summarize(outcomes: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    def agg(g: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "n": len(g),
                "pun_95_pct": 100 * (g["actual_rate"] >= FULL_THRESHOLDS[0]).mean(),
                "pun_90_pct": 100 * (g["actual_rate"] >= FULL_THRESHOLDS[1]).mean(),
                "hodanje_km": g["walk_km"].mean(),
                "voznja_km": g["drive_km"].mean(),
                "zauzetost_pri_dolasku_pct": 100 * g["actual_rate"].mean(),
                # samo pravi Park & Ride (B&Q Boundary Road je tip "ostalo")
                "p_and_r_pct": 100 * g["p_and_r"].astype(bool).mean(),
            }
        )

    order = {s: i for i, s in enumerate(STRATEGIES)}
    table = outcomes.groupby(by).apply(agg, include_groups=False).reset_index()
    table["_order"] = table["strategy"].map(order)
    sort_cols = [c for c in by if c != "strategy"] + ["_order"]
    return table.sort_values(sort_cols).drop(columns="_order").round(2)


# Boje: validirana kategorijska paleta (dataviz skill) - plava/narandzasta/aqua
# za tri prognoze, siva za referentnu strategiju "najblizi". Identitet nikad
# samo bojom: svaka linija ima i oblik markera, a krajnje tacke direktnu oznaku.
PLOT_STYLE = {
    "najblizi": {"color": "#898781", "marker": "s", "linestyle": "-", "label": "najbliži destinaciji"},
    "naivna": {"color": "#eb6834", "marker": "^", "linestyle": "-", "label": "preporuka, naivna prognoza"},
    "model": {"color": "#2a78d6", "marker": "o", "linestyle": "-", "label": "preporuka, XGBoost"},
    "oracle": {"color": "#1baf7a", "marker": "D", "linestyle": "--", "label": "preporuka, savršena prognoza"},
}
SCENARIO_TITLE = {"svi_parkinzi": "Svi parkinzi (uklj. P&R)", "samo_gradski": "Samo gradski parkinzi"}
INK, MUTED, GRID = "#21201c", "#52514e", "#e4e3dc"


def _style_axes(ax) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)


def _marker_fill(strategy: str) -> dict:
    # Oracle je cesto na istim vrednostima kao model - suplji marker i
    # isprekidana linija, da se model vidi ispod njega.
    return {"markerfacecolor": "white"} if strategy == "oracle" else {}


def _annotate_line_ends(ax, x: float, values: list[float], min_gap: float) -> None:
    """Direktne oznake krajnjih vrednosti; bliske vrednosti se razmicu
    vertikalno, a identicne spajaju u jednu oznaku, da se ne preklapaju."""
    unique = sorted(set(round(v, 1) for v in values))
    positions = []
    for v in unique:
        y = v if not positions else max(v, positions[-1] + min_gap)
        positions.append(y)
    for v, y in zip(unique, positions):
        ax.annotate(
            f"{v:.1f}%", (x, v), xytext=(x + 0.12, y), textcoords="data",
            va="center", fontsize=8, color=INK,
        )


def _save(fig, name: str) -> None:
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=200)
    print(f"Sacuvan grafik: {path}")


def plot_lead_times(main_table: pd.DataFrame) -> None:
    """% dolazaka na pun parking u zavisnosti od toga koliko unapred vozac
    planira - jedan panel po scenariju, ista y osa."""
    import matplotlib.pyplot as plt

    y_max = main_table["pun_95_pct"].max()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, scenario in zip(axes, SCENARIO_TITLE):
        data = main_table[main_table["scenario"] == scenario]
        end_labels = []
        for strategy, style in PLOT_STYLE.items():
            s = data[data["strategy"] == strategy]
            ax.plot(
                s["lead_min"] / 60, s["pun_95_pct"], color=style["color"], marker=style["marker"],
                linestyle=style["linestyle"], linewidth=2, markersize=6, label=style["label"],
                **_marker_fill(strategy),
            )
            end_labels.append(s.iloc[-1]["pun_95_pct"])
        _annotate_line_ends(ax, LEAD_TIMES_MIN[-1] / 60, end_labels, min_gap=0.05 * y_max)
        ax.set_title(SCENARIO_TITLE[scenario], fontsize=10, color=INK, loc="left")
        ax.set_xlabel("Koliko unapred vozač planira (h)", fontsize=9, color=MUTED)
        ax.set_xticks([lead / 60 for lead in LEAD_TIMES_MIN])
        ax.set_xlim(-0.2, LEAD_TIMES_MIN[-1] / 60 + 0.8)
        _style_axes(ax)
    axes[0].set_ylabel("Dolazak na pun parking (≥95%), % vožnji", fontsize=9, color=MUTED)
    axes[0].set_ylim(bottom=-0.6)  # linija na 0% da se ne lepi za osu
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    _save(fig, "eval_recommender_po_planiranju.png")
    plt.close(fig)


def plot_tradeoff(sweep: pd.DataFrame) -> None:
    """Kompromis rizik punog parkinga / hodanje pri promeni pondera w1
    (dostupnost) naspram w2 = 1 - w1 (blizina). Samo gradski parkinzi - sa P&R
    "hodanje" od 4-5 km nije realno hodanje (ide se autobusom)."""
    import matplotlib.pyplot as plt

    data = sweep[sweep["scenario"] == "samo_gradski"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, lead in zip(axes, SWEEP_LEAD_TIMES_MIN):
        lead_data = data[data["lead_min"] == lead]
        for strategy in ["naivna", "model", "oracle"]:
            style = PLOT_STYLE[strategy]
            s = lead_data[lead_data["strategy"] == strategy].sort_values("w1")
            ax.plot(
                s["hodanje_km"] * 1000, s["pun_95_pct"], color=style["color"], marker=style["marker"],
                linestyle=style["linestyle"], linewidth=2, markersize=5, label=style["label"],
                **_marker_fill(strategy),
            )
        # Oznake w1 samo na krivoj modela - selektivno, ne na svakoj tacki.
        model = lead_data[lead_data["strategy"] == "model"].sort_values("w1")
        for _, row in model.iterrows():
            if row["w1"] in (0.0, 0.3, 0.5, 0.7, 1.0):
                ax.annotate(
                    f"w1={row['w1']:.1f}", (row["hodanje_km"] * 1000, row["pun_95_pct"]),
                    xytext=(5, 5), textcoords="offset points", fontsize=8, color=INK,
                )
        title = "Polazak odmah" if lead == 0 else f"Planiranje {lead // 60} h unapred"
        ax.set_title(f"{title} · samo gradski parkinzi", fontsize=10, color=INK, loc="left")
        ax.set_xlabel("Prosečno hodanje do destinacije (m)", fontsize=9, color=MUTED)
        _style_axes(ax)
    axes[0].set_ylabel("Dolazak na pun parking (≥95%), % vožnji", fontsize=9, color=MUTED)
    axes[0].set_ylim(bottom=-0.6)  # linija na 0% da se ne lepi za osu
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    _save(fig, "eval_recommender_osetljivost.png")
    plt.close(fig)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)

    print("Ucitavam podatke i model...")
    source = ReplaySource(city=CITY)
    # Isti kandidati kao u API-ju: sa koordinatama i tipom koji se preporucuje.
    parks = [
        p for p in parks_module.load_parks(CITY)
        if p["lat"] is not None and p["type"] in recommender.RECOMMENDABLE_TYPES
    ]
    trips = generate_trips(rng)
    print(f"{len(trips)} vozaca, {len(parks)} parkinga sa koordinatama, vremena planiranja {LEAD_TIMES_MIN} min")

    print("Racunam dolaske i predikcije...")
    options = build_options(trips, source, parks)

    scenarios = {
        "svi_parkinzi": group_options(options),
        "samo_gradski": group_options(options[options["city_park"]]),
    }

    # 1) Glavna tabela - podrazumevani ponderi iz recommender.py
    tables = []
    peak_tables = []
    for name, groups in scenarios.items():
        outcomes = simulate(groups, STRATEGIES, DEFAULT_WEIGHTS, SEED)
        table = summarize(outcomes, ["lead_min", "strategy"])
        table.insert(0, "scenario", name)
        tables.append(table)

        # Podskup gde je izbor najtezi: subota 11-16h (centar cesto pun)
        peak = outcomes[(outcomes["now"].dt.dayofweek == 5) & outcomes["now"].dt.hour.between(11, 15)]
        peak_table = summarize(peak, ["lead_min", "strategy"])
        peak_table.insert(0, "scenario", name)
        peak_tables.append(peak_table)

    main_table = pd.concat(tables, ignore_index=True)
    peak_table = pd.concat(peak_tables, ignore_index=True)
    main_table.to_csv(os.path.join(OUTPUT_DIR, "eval_recommender_strategije.csv"), index=False)
    peak_table.to_csv(os.path.join(OUTPUT_DIR, "eval_recommender_subota_vrhunac.csv"), index=False)

    # 2) Osetljivost pondera (w3 = 0, w2 = 1 - w1), za polazak odmah i za
    #    planiranje 2h unapred - tu se prognoze najvise razlikuju.
    sweep_rows = []
    for name, groups in scenarios.items():
        for lead in SWEEP_LEAD_TIMES_MIN:
            lead_groups = [g for g in groups if g[0]["lead_min"] == lead]
            for w1 in WEIGHT_SWEEP_W1:
                weights = (w1, round(1 - w1, 1), 0.0)
                outcomes = simulate(lead_groups, ["naivna", "model", "oracle"], weights, SEED)
                table = summarize(outcomes, ["strategy"])
                table.insert(0, "w1", w1)
                table.insert(0, "lead_min", lead)
                table.insert(0, "scenario", name)
                sweep_rows.append(table)
    sweep = pd.concat(sweep_rows, ignore_index=True)
    sweep.to_csv(os.path.join(OUTPUT_DIR, "eval_recommender_osetljivost.csv"), index=False)

    pd.set_option("display.width", 200)
    cols = ["scenario", "lead_min", "strategy", "n", "pun_95_pct", "pun_90_pct", "hodanje_km", "voznja_km", "p_and_r_pct"]
    print("\n=== Strategije (podrazumevani ponderi", DEFAULT_WEIGHTS, ") ===")
    print(main_table[cols].to_string(index=False))
    print("\n=== Subota 11-16h ===")
    print(peak_table[cols].to_string(index=False))
    print("\n=== Osetljivost pondera (w3=0) ===")
    sweep_cols = ["scenario", "lead_min", "w1", "strategy", "pun_95_pct", "hodanje_km", "p_and_r_pct"]
    print(sweep[sweep_cols].to_string(index=False))

    plot_lead_times(main_table)
    plot_tradeoff(sweep)


if __name__ == "__main__":
    main()
