"""
Slike za pisani rad (korak 9) koje ne pravi nijedan od eksperimenata.

Poglavlje 3.1 (vremenske serije):
  rad_3_1_nedeljni_tok.png      zauzetost gradskog i P&R parkinga kroz jednu nedelju
  rad_3_2_autokorelacija.png    autokorelacija zauzetosti za pomake do dve nedelje
Poglavlje 3.2 (prognoza kao nadgledano ucenje):
  rad_3_3_primer_za_ucenje.png  sema: koji ulazi su poznati u trenutku t, sta je cilj
Poglavlje 3.3 (pravilna evaluacija):
  rad_3_4_podela_podataka.png   hronoloska podela: trening, validacija i test
Poglavlje 4.1 (stabla odlucivanja):
  rad_4_1_malo_stablo.png       stablo dubine 2 nauceno na nasim podacima
  rad_4_2_dubina_stabla.png     greska jednog stabla na treningu i testu u zavisnosti od dubine
Poglavlje 4.2 (bagging i Random Forest):
  rad_4_3_broj_stabala.png      greska na testu u zavisnosti od broja stabala (bagging i Random Forest)
Poglavlje 4.3 (gradient boosting):
  rad_4_4_boosting_iteracije.png  greska XGBoost-a na treningu i testu posle svakog dodatog stabla
Poglavlje 4.5 (Ridge):
  rad_4_5_linearni_koeficijenti.png  koeficijenti linearne regresije po horizontu naspram jednog modela
Poglavlje 6 (podaci):
  rad_6_1_lokacije.png          polozaj 15 parkinga u odnosu na centar Norwicha (celo podrucje i centar)
  rad_6_2_kopirane_nedelje.png  tri uzastopna utorka: B&Q (kopija prethodne nedelje) naspram The Foruma
  rad_6_tabela_parkinga.csv     naziv, tip, kapacitet i prosecna zauzetost parkinga (tabela 6.2)
Poglavlje 7 (model predikcije), iz sacuvanih rezultata koraka 4, 5 i 7 (bez novog treniranja):
  rad_7_1_poredjenje_modela.png  MAE po horizontu: modeli i referentne prognoze
  rad_7_2_greske.png             a) MAE po satu (gradski / P&R), b) MAE po stvarnoj popunjenosti
  rad_7_3_gradovi.png            MAE po horizontu, sopstveni model svakog grada
  rad_7_4_prenos.png             prenos Norfolk modela na druge gradove
Poglavlje 8 (sistem preporuke):
  rad_8_1_delovi_skora.png       sema tri dela skora: vreme voznje, blizina cilju, dostupnost pri dolasku
  rad_8_2_izbor_pondera.png      izbor pondera na oktobru 2017: 231 kombinacija i Pareto front (iz koraka 6b)
Poglavlje 9 (arhitektura):
  rad_9_1_arhitektura.png        moduli sistema: priprema i ucenje, backend, frontend
  (snimci ekrana aplikacije nisu iz ovog skripta: rad_9_*_*.png iz headless Chrome-a, vidi PROGRESS.md)
Poglavlje 4.6 (SHAP i ablacija), iz sacuvanih rezultata koraka 5 (ml/analyze_model.py):
  rad_4_6_shap.png              prosecan |SHAP| doprinos ulaza po grupi horizonata
  rad_4_7_ablacija.png          greska po horizontu za model bez pojedinih grupa ulaza

Slike nemaju naslov u samoj slici: u radu naslov ide u natpis ispod slike
(„Slika 3.1. ...”), po uputstvu „Forma master rada”. Natpisi su na srpskom, a ose
imaju jedinice.

Koriste se samo podaci za trening (pre 1.10.2017). B&Q Boundary Road se ne
koristi za autokorelaciju, jer su njegovi podaci velikim delom kopija prethodne
nedelje (PROGRESS.md, korak 7) i vestacki bi podigli autokorelaciju na 7 dana.

Pokretanje (iz korena projekta):
    python ml/thesis_figures.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from backend import parks as parks_module  # noqa: E402
from ml.data_prep import CITY_CONFIGS, STEPS_PER_DAY, load_raw, resample_per_park  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TRAIN_END = CITY_CONFIGS["norfolk"]["test_start"]

WEEK_START = pd.Timestamp("2017-09-11")  # ponedeljak; nedelja sa punim merenjima
WEEK_PARKS = {"CPN0009": "The Forum (gradski parking)", "CPN0016": "Thickthorn (Park & Ride)"}
MAX_LAG_DAYS = 14
EXCLUDED_FROM_ACF = {"C06391"}  # B&Q Boundary Road: kopirani podaci

# Validirana kategorijska paleta (dataviz, kao u ml/eval_recommender.py):
# gradski parkinzi plavo, Park & Ride narandzasto.
COLORS = {"grad": "#2a78d6", "Park & Ride": "#eb6834"}
INK, MUTED, GRID = "#21201c", "#52514e", "#e4e3dc"
DAY_NAMES = ["pon", "uto", "sre", "čet", "pet", "sub", "ned"]
# Sirina slike = sirina teksta u radu (16 cm), da natpisi od 8-9 pt ostanu te velicine na papiru.
FIG_WIDTH_IN = 6.3


def _style_axes(ax) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.8)
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


def plot_week(series: dict[str, pd.Series], types: dict[str, str]) -> None:
    """Slika 3.1: dnevna i nedeljna sezonalnost na dva parkinga razlicitog tipa.
    Prekidi linije su noci (merenja samo 08-23 h)."""
    import matplotlib.pyplot as plt

    week = pd.date_range(WEEK_START, WEEK_START + pd.Timedelta(days=7), freq="30min", inclusive="left")
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    for park_id, label in WEEK_PARKS.items():
        values = series[park_id].reindex(week) * 100
        ax.plot(week, values, color=COLORS[types[park_id]], linewidth=1.8, label=label)
    ticks = [WEEK_START + pd.Timedelta(days=d, hours=12) for d in range(7)]
    ax.set_xticks(ticks, [f"{DAY_NAMES[d]} {t.day}.{t.month}." for d, t in enumerate(ticks)])
    for d in range(1, 7):
        ax.axvline(WEEK_START + pd.Timedelta(days=d), color=GRID, linewidth=0.8, zorder=0)
    ax.set_xlim(week[0], week[-1])
    ax.set_ylim(0, 118)  # prostor iznad 100% za legendu, da ne prekriva vrhove
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("Zauzetost (%)", fontsize=9, color=MUTED)
    ax.set_xlabel("Dan u nedelji (11–17. septembar 2017)", fontsize=9, color=MUTED)
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
    fig.tight_layout()
    _save(fig, "rad_3_1_nedeljni_tok.png")
    plt.close(fig)


MIN_PAIRS = 1000  # pomak sa manje parova merenja daje nepouzdanu (sumnu) procenu


def autocorrelation(series: pd.Series, max_lag: int) -> np.ndarray:
    """Autokorelacija za pomake 1..max_lag koraka od 30 min. Racuna se samo na
    parovima gde postoje obe vrednosti (rupe i noci se ne popunjavaju); pomaci
    sa manje od MIN_PAIRS parova se izostavljaju (npr. P&R, koji radi kraci deo dana)."""
    present = series.notna()
    values = []
    for lag in range(1, max_lag + 1):
        pairs = int((present & present.shift(lag, fill_value=False)).sum())
        values.append(series.autocorr(lag) if pairs >= MIN_PAIRS else np.nan)
    return np.array(values)


def plot_autocorrelation(acf_by_type: dict[str, np.ndarray]) -> None:
    """Slika 3.2: prosecna autokorelacija po tipu parkinga; vrhovi na 1 i 7 dana."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    for park_type, acf in acf_by_type.items():
        lags_days = np.arange(1, len(acf) + 1) / STEPS_PER_DAY
        label = "gradski parkinzi" if park_type == "grad" else "Park & Ride parkinzi"
        ax.plot(lags_days, acf, color=COLORS[park_type], linewidth=1.6, label=label)
    for day, text in ((1, "1 dan: isto vreme juče"), (7, "7 dana: isto vreme pre nedelju dana")):
        ax.axvline(day, color=MUTED, linewidth=0.9, linestyle=":")
        ax.annotate(text, (day, 1.08), xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.set_xticks(range(0, MAX_LAG_DAYS + 1))
    ax.set_xlim(0, MAX_LAG_DAYS)
    ax.set_ylim(-0.6, 1.2)  # prostor iznad krivih za natpise
    ax.set_yticks([-0.5, 0, 0.5, 1.0])
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xlabel("Pomak (dani)", fontsize=9, color=MUTED)
    ax.set_ylabel("Autokorelacija", fontsize=9, color=MUTED)
    _style_axes(ax)
    # Legenda iznad grafika, da ne prekriva natpise na 1 i 7 dana.
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, "rad_3_2_autokorelacija.png")
    plt.close(fig)


def plot_supervised_example() -> None:
    """Slika 3.3: sema (nije u razmeri) jednog primera za ucenje. Ulazi su
    vrednosti poznate u trenutku t, cilj je zauzetost u trenutku t + h."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch

    recent, seasonal, target = "#2a78d6", "#1baf7a", "#eb6834"  # validirana paleta (dataviz)
    x = {"lastweek": 0.6, "yesterday": 2.4, "t2": 4.2, "t1": 4.75, "t": 5.3, "target": 7.6}
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.3625))
    # Vremenska osa sa prekidima (sema nije u razmeri).
    for a, b in ((0.0, 1.35), (1.65, 3.15), (3.45, 8.4)):
        ax.plot([a, b], [0, 0], color=MUTED, linewidth=1.2)
    for gap in (1.5, 3.3):
        ax.text(gap, 0, "//", ha="center", va="center", fontsize=11, color=MUTED)
    ax.annotate("", (8.55, 0), (8.35, 0), arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.2))
    ax.text(8.55, -0.28, "vreme", ha="right", fontsize=8, color=MUTED)
    ax.plot([x["t"], x["t"]], [-0.15, 1.35], color=INK, linewidth=1, linestyle="--")
    ax.text(x["t"], 1.45, "sada (trenutak prognoze)", ha="center", fontsize=8, color=INK)

    points = [
        ("lastweek", "t+h−7 dana", seasonal, "s"), ("yesterday", "t+h−1 dan", seasonal, "s"),
        ("t2", "t−2", recent, "o"), ("t1", "t−1", recent, "o"), ("t", "t", recent, "o"),
        ("target", "t+h", target, "D"),
    ]
    for key, label, color, marker in points:
        ax.plot(x[key], 0, marker=marker, markersize=9, color=color, markeredgecolor="white", zorder=3)
        ax.text(x[key], -0.32, label, ha="center", va="top", fontsize=8, color=INK)

    ax.text(x["t"] - 0.12, 0.42, "ulazi: poslednje vrednosti\ny(t), y(t−1), y(t−2)", ha="right", fontsize=8,
            color=recent)
    ax.text((x["lastweek"] + x["yesterday"]) / 2, 0.42, "ulazi: isto vreme kao cilj, ranije\n(pre nedelju dana i juče)",
            ha="center", fontsize=8, color=seasonal)
    ax.text(x["target"], 0.42, "izlaz: y(t+h)", ha="center", fontsize=8, color=target)
    ax.text(x["target"], -0.75, "ulaz: kalendar ciljnog trenutka\n(sat, dan, vikend, praznik)", ha="center",
            va="top", fontsize=8, color=INK)
    horizon = FancyArrowPatch((x["t"], 1.05), (x["target"], 1.05), arrowstyle="<->", mutation_scale=10,
                              color=INK, linewidth=1)
    ax.add_patch(horizon)
    ax.text((x["t"] + x["target"]) / 2, 1.13, "horizont h (i on je ulaz)", ha="center", fontsize=8, color=INK)

    ax.set_xlim(-0.1, 8.7)
    ax.set_ylim(-1.35, 1.7)
    ax.axis("off")
    fig.tight_layout()
    _save(fig, "rad_3_3_primer_za_ucenje.png")
    plt.close(fig)


MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"]


def plot_data_split() -> None:
    """Slika 3.4: hronoloska podela podataka za model predikcije i za izbor
    pondera preporuke (validacija oktobar, test novembar-decembar)."""
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    train_c, valid_c, test_c = "#2a78d6", "#1baf7a", "#eb6834"  # validirana paleta (dataviz)
    start, cut = pd.Timestamp("2016-10-26"), pd.Timestamp("2017-10-01")
    nov, end = pd.Timestamp("2017-11-01"), pd.Timestamp("2017-12-06")
    rows = [
        ("Model predikcije", [(start, cut, train_c, "trening (11 meseci)"), (cut, end, test_c, "test")]),
        ("Izbor pondera preporuke", [(cut, nov, valid_c, None), (nov, end, test_c, "test")]),
    ]
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.3))
    for y, (_, bars) in enumerate(reversed(rows)):
        for a, b, color, label in bars:
            ax.barh(y, b - a, left=a, height=0.55, color=color, edgecolor="white", linewidth=1.5)
            if label:
                ax.text(a + (b - a) / 2, y, label, ha="center", va="center", fontsize=8, color="white")
    # Traka za oktobar je preuska za natpis - natpis levo od nje, u boji trake.
    ax.text(cut - pd.Timedelta(days=6), 0, "validacija (oktobar)", ha="right", va="center", fontsize=8, color=valid_c)
    ax.set_yticks(range(len(rows)), [name for name, _ in reversed(rows)])
    ax.axvline(cut, color=INK, linewidth=1, linestyle="--")
    ax.text(cut, 1.48, "1.10.2017: model vidi samo podatke pre ove granice", ha="right", fontsize=8, color=INK)
    ax.set_xlim(start - pd.Timedelta(days=5), end + pd.Timedelta(days=5))
    ax.set_ylim(-0.5, 1.75)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _: f"{MONTHS[mdates.num2date(v).month - 1]} {mdates.num2date(v).year}"))
    _style_axes(ax)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=9, colors=INK)
    fig.tight_layout()
    _save(fig, "rad_3_4_podela_podataka.png")
    plt.close(fig)


TREE_FEATURES = {"y_t": "zauzetost sada", "y_lastweek": "isto vreme pre 7 dana", "horizon_minutes": "horizont"}
TREE_DEPTHS = [1, 2, 3, 4, 6, 8, 10, 12, 15, 20, 25]
TREE_SAMPLE = 500_000  # deo trening skupa za stabla, zbog brzine
XGBOOST_MAE = 4.83  # model iz aplikacije (PROGRESS.md, korak 4)


def _tree_label(feature: str, threshold: float) -> str:
    if feature == "horizon_minutes":
        return f"{TREE_FEATURES[feature]} ≤ {threshold / 60:.1f} h?".replace(".", ",")
    return f"{TREE_FEATURES[feature]} ≤ {threshold * 100:.0f}%?"


def plot_small_tree(train: pd.DataFrame) -> None:
    """Slika 4.1: stablo dubine 2 nauceno na delu trening skupa, sa samo tri
    ulaza, nacrtano sa pitanjima na srpskom (u cvorovima) i prognozom (u listovima)."""
    import matplotlib.pyplot as plt
    from sklearn.tree import DecisionTreeRegressor

    sample = train.sample(TREE_SAMPLE, random_state=0)
    features = list(TREE_FEATURES)
    tree = DecisionTreeRegressor(max_depth=2, min_samples_leaf=1000, random_state=0)
    tree.fit(sample[features], sample["target"])
    t = tree.tree_

    # Cvorovi u redosledu sklearn-a: 0 koren, zatim levo podstablo pa desno.
    positions, depth_of = {}, {}

    def place(node, x, width, depth):
        positions[node], depth_of[node] = (x, 0.88 - depth * 0.38), depth
        if t.children_left[node] != -1:
            place(t.children_left[node], x - width / 2, width / 2, depth + 1)
            place(t.children_right[node], x + width / 2, width / 2, depth + 1)

    place(0, 0.5, 0.5, 0)
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    total = t.n_node_samples[0]
    for node, (x, y) in positions.items():
        left, right = t.children_left[node], t.children_right[node]
        if left != -1:
            for child, answer in ((left, "da"), (right, "ne")):
                cx, cy = positions[child]
                ax.plot([x, cx], [y - 0.06, cy + 0.07], color=MUTED, linewidth=1, zorder=1)
                ax.text((x + cx) / 2 + (-0.02 if answer == "da" else 0.02), (y + cy) / 2, answer,
                        ha="right" if answer == "da" else "left", va="center", fontsize=8, color=MUTED)
            text, face = _tree_label(features[t.feature[node]], t.threshold[node]), "#eef3fb"
        else:
            share = 100 * t.n_node_samples[node] / total
            text, face = f"prognoza: {t.value[node][0][0] * 100:.0f}%\n({share:.0f}% primera)", "#fdf0ea"
        ax.text(x, y, text, ha="center", va="center", fontsize=8, color=INK, zorder=2,
                bbox=dict(boxstyle="round,pad=0.45", facecolor=face, edgecolor=MUTED, linewidth=0.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.tight_layout()
    _save(fig, "rad_4_1_malo_stablo.png")
    plt.close(fig)


def plot_tree_depth(train: pd.DataFrame, test: pd.DataFrame) -> None:
    """Slika 4.2: greska jednog stabla (svi ulazi) na treningu i testu za razne
    dubine - plitko stablo je pregrubo, duboko "uci napamet" trening."""
    import matplotlib.pyplot as plt
    from sklearn.tree import DecisionTreeRegressor

    from ml.data_prep import FEATURES

    def model_input(frame):
        x = frame[FEATURES].copy()
        x["carpark"] = x["carpark"].cat.codes  # jedno stablo: sifra parkinga kao broj
        return x

    sample = train.sample(TREE_SAMPLE, random_state=0)
    x_train, x_test = model_input(sample), model_input(test)
    rows = []
    for depth in TREE_DEPTHS:
        tree = DecisionTreeRegressor(max_depth=depth, min_samples_leaf=1, random_state=0).fit(x_train, sample["target"])
        rows.append({
            "dubina": depth,
            "MAE_trening": 100 * np.abs(tree.predict(x_train) - sample["target"].to_numpy()).mean(),
            "MAE_test": 100 * np.abs(tree.predict(x_test) - test["target"].to_numpy()).mean(),
        })
        print(f"  dubina {depth}: trening {rows[-1]['MAE_trening']:.2f}, test {rows[-1]['MAE_test']:.2f}")
    table = pd.DataFrame(rows)
    table.round(3).to_csv(os.path.join(OUTPUT_DIR, "rad_4_2_dubina_stabla.csv"), index=False)

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    ax.plot(table["dubina"], table["MAE_trening"], color=COLORS["grad"], marker="o", markersize=4, linewidth=1.8,
            label="jedno stablo, trening")
    ax.plot(table["dubina"], table["MAE_test"], color=COLORS["Park & Ride"], marker="s", markersize=4, linewidth=1.8,
            label="jedno stablo, test")
    ax.axhline(XGBOOST_MAE, color=INK, linewidth=1, linestyle="--", label="XGBoost (400 stabala dubine 6), test")
    best = table.loc[table["MAE_test"].idxmin()]
    ax.annotate(f"najmanja greška na testu:\ndubina {best['dubina']:.0f}, MAE {best['MAE_test']:.2f}".replace(".", ","),
                (best["dubina"], best["MAE_test"]), xytext=(10, 18), textcoords="offset points", fontsize=8,
                color=INK, arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.8))
    ax.set_xlabel("Dubina stabla", fontsize=9, color=MUTED)
    ax.set_ylabel("MAE (p.p.)", fontsize=9, color=MUTED)
    ax.set_ylim(bottom=0)
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    fig.tight_layout()
    _save(fig, "rad_4_2_dubina_stabla.png")
    plt.close(fig)


BEST_SINGLE_TREE_MAE = 5.90  # slika 4.2, dubina 12


def plot_forest_size(train: pd.DataFrame, test: pd.DataFrame) -> None:
    """Slika 4.3: greska na testu kada se prognoze prvih B stabala usrednje, za
    bagging (svaka podela bira izmedju svih ulaza) i Random Forest (izmedju
    nasumicne polovine ulaza). Podesavanja su ista kao u ml/compare_models.py
    (100 stabala, svako vidi 10% trening skupa, najmanje 5 primera u listu)."""
    import matplotlib.pyplot as plt
    from sklearn.ensemble import RandomForestRegressor

    from ml.compare_models import make_random_forest, tree_input

    x_train, x_test = tree_input(train), tree_input(test).to_numpy(dtype=np.float32)
    y_test = test["target"].to_numpy()
    variants = {
        "Random Forest (polovina ulaza po podeli)": make_random_forest(),
        "bagging (svi ulazi po podeli)": RandomForestRegressor(**{**make_random_forest().get_params(), "max_features": 1.0}),
    }
    curves = {}
    for name, forest in variants.items():
        print(f"  {name}...")
        forest.fit(x_train, train["target"])
        running, maes = np.zeros(len(y_test)), []
        for b, tree in enumerate(forest.estimators_, start=1):
            running += tree.predict(x_test)
            maes.append(100 * np.abs(np.clip(running / b, 0, 1) - y_test).mean())
        curves[name] = np.array(maes)
        print(f"    1 stablo: {maes[0]:.2f}, 10: {maes[9]:.2f}, 100: {maes[-1]:.2f}")
    pd.DataFrame({"broj_stabala": np.arange(1, len(maes) + 1), **curves}).round(3).to_csv(
        os.path.join(OUTPUT_DIR, "rad_4_3_broj_stabala.csv"), index=False)

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    styles = {"Random Forest (polovina ulaza po podeli)": COLORS["grad"], "bagging (svi ulazi po podeli)": "#1baf7a"}
    for name, maes in curves.items():
        ax.plot(np.arange(1, len(maes) + 1), maes, color=styles[name], linewidth=1.8, label=name)
    ax.axhline(BEST_SINGLE_TREE_MAE, color=MUTED, linewidth=1, linestyle=":", label="najbolje jedno stablo (dubina 12)")
    ax.axhline(XGBOOST_MAE, color=INK, linewidth=1, linestyle="--", label="XGBoost (400 stabala)")
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 5, 10, 20, 50, 100], ["1", "2", "5", "10", "20", "50", "100"])
    ax.set_xlabel("Broj stabala u ansamblu (logaritamska skala)", fontsize=9, color=MUTED)
    ax.set_ylabel("MAE na testu (p.p.)", fontsize=9, color=MUTED)
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    fig.tight_layout()
    _save(fig, "rad_4_3_broj_stabala.png")
    plt.close(fig)


BOOSTING_ROUNDS = 800
APP_MODEL_ROUNDS = 400  # model u aplikaciji (ml/train_norfolk.py)


def plot_boosting_rounds(train: pd.DataFrame, test: pd.DataFrame) -> None:
    """Slika 4.4: MAE na treningu i testu posle svakog dodatog stabla, za XGBoost
    sa parametrima modela iz aplikacije (osim broja stabala)."""
    import joblib
    import matplotlib.pyplot as plt
    import xgboost as xgb

    from ml.data_prep import FEATURES

    params = joblib.load(os.path.join(os.path.dirname(__file__), "model_norfolk.joblib"))["model"].get_params()
    params.update(n_estimators=BOOSTING_ROUNDS, n_jobs=8, eval_metric="mae")
    model = xgb.XGBRegressor(**params)
    test = test.assign(carpark=pd.Categorical(test["carpark"].astype(str), categories=train["carpark"].cat.categories))
    model.fit(train[FEATURES], train["target"], eval_set=[(train[FEATURES], train["target"]),
                                                          (test[FEATURES], test["target"])], verbose=False)
    history = model.evals_result()
    curves = {"trening": 100 * np.array(history["validation_0"]["mae"]),
              "test": 100 * np.array(history["validation_1"]["mae"])}
    rounds = np.arange(1, BOOSTING_ROUNDS + 1)
    pd.DataFrame({"broj_stabala": rounds, **{f"MAE_{k}": v for k, v in curves.items()}}).round(3).to_csv(
        os.path.join(OUTPUT_DIR, "rad_4_4_boosting_iteracije.csv"), index=False)
    for b in (1, 10, 50, 100, 200, 400, 800):
        print(f"  {b} stabala: trening {curves['trening'][b - 1]:.2f}, test {curves['test'][b - 1]:.2f}")
    draw_boosting_rounds()


def draw_boosting_rounds() -> None:
    """Crta sliku 4.4 iz sacuvanog CSV-a: (a) ceo tok, (b) uvecano 100-800 stabala,
    gde se vidi razdvajanje greske na treningu i testu."""
    import matplotlib.pyplot as plt

    table = pd.read_csv(os.path.join(OUTPUT_DIR, "rad_4_4_boosting_iteracije.csv"))
    fig, (ax_all, ax_zoom) = plt.subplots(1, 2, figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.42))
    for ax in (ax_all, ax_zoom):
        ax.plot(table["broj_stabala"], table["MAE_trening"], color=COLORS["grad"], linewidth=1.8, label="trening")
        ax.plot(table["broj_stabala"], table["MAE_test"], color=COLORS["Park & Ride"], linewidth=1.8, label="test")
        ax.axvline(APP_MODEL_ROUNDS, color=MUTED, linewidth=1, linestyle=":")
        _style_axes(ax)
        ax.set_xlabel("Broj stabala", fontsize=9, color=MUTED)
    ax_all.set_xscale("log")
    ax_all.set_xticks([1, 10, 100, 800], ["1", "10", "100", "800"])
    ax_all.set_ylim(0, 27)
    ax_all.set_ylabel("MAE (p.p.)", fontsize=9, color=MUTED)
    ax_all.set_title("a) ceo tok (logaritamska skala)", fontsize=9, color=INK, loc="left")
    zoom = table[table["broj_stabala"] >= 100]
    ax_zoom.set_xlim(100, BOOSTING_ROUNDS)
    ax_zoom.set_ylim(3.8, 5.6)
    ax_zoom.set_title("b) uvećano: od 100 do 800 stabala", fontsize=9, color=INK, loc="left")
    ax_zoom.annotate(f"model u aplikaciji: {APP_MODEL_ROUNDS} stabala", (APP_MODEL_ROUNDS, 3.92), xytext=(5, 0),
                     textcoords="offset points", ha="left", va="center", fontsize=8, color=INK)
    for col, color in (("MAE_trening", COLORS["grad"]), ("MAE_test", COLORS["Park & Ride"])):
        last = zoom[col].iloc[-1]
        ax_zoom.annotate(f"{last:.2f}".replace(".", ","), (BOOSTING_ROUNDS, last), xytext=(-2, 6),
                         textcoords="offset points", ha="right", fontsize=8, color=color)
    handles, labels = ax_all.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    _save(fig, "rad_4_4_boosting_iteracije.png")
    plt.close(fig)


LINEAR_FEATURES = {"y_t": "zauzetost sada", "y_yesterday": "isto vreme juče", "y_lastweek": "isto vreme pre 7 dana"}
LINEAR_COLORS = {"y_t": "#2a78d6", "y_yesterday": "#eb6834", "y_lastweek": "#1baf7a"}  # validirana paleta


def _ols(frame: pd.DataFrame) -> np.ndarray:
    """Obicna linearna regresija sa slobodnim clanom: [b0, b_y_t, b_y_yesterday, b_y_lastweek]."""
    x = np.column_stack([np.ones(len(frame))] + [frame[f].to_numpy() for f in LINEAR_FEATURES])
    return np.linalg.lstsq(x, frame["target"].to_numpy(), rcond=None)[0]


def _ols_mae(frame: pd.DataFrame, coef: np.ndarray) -> float:
    x = np.column_stack([np.ones(len(frame))] + [frame[f].to_numpy() for f in LINEAR_FEATURES])
    return 100 * np.abs(np.clip(x @ coef, 0, 1) - frame["target"].to_numpy()).mean()


def plot_linear_coefficients(train: pd.DataFrame, test: pd.DataFrame) -> None:
    """Slika 4.5: koeficijenti linearne regresije (tri ulaza) naucene posebno za
    svaki horizont, naspram jednog modela za sve horizonte. Pokazuje interakciju
    horizonta i trenutnog stanja koju jedan linearni model ne moze da nauci."""
    import matplotlib.pyplot as plt

    cols = list(LINEAR_FEATURES) + ["target", "horizon_minutes"]
    train = train[cols].dropna()
    test = test[cols].dropna()
    pooled = _ols(train)
    per_h = {h: _ols(g) for h, g in train.groupby("horizon_minutes")}
    mae_pooled = _ols_mae(test, pooled)
    mae_per_h = 100 * np.mean(np.concatenate([
        np.abs(np.clip(np.column_stack([np.ones(len(g))] + [g[f].to_numpy() for f in LINEAR_FEATURES]) @ per_h[h], 0, 1)
               - g["target"].to_numpy()) for h, g in test.groupby("horizon_minutes")]))
    rows = [{"horizont_min": h, **{f: c[i + 1] for i, f in enumerate(LINEAR_FEATURES)}} for h, c in per_h.items()]
    table = pd.DataFrame(rows)
    table.round(4).to_csv(os.path.join(OUTPUT_DIR, "rad_4_5_linearni_koeficijenti.csv"), index=False)
    print("  jedan model za sve horizonte:", {f: round(pooled[i + 1], 3) for i, f in enumerate(LINEAR_FEATURES)})
    print(table[table["horizont_min"].isin([30, 120, 240, 480, 900])].round(3).to_string(index=False))
    print(f"  MAE na testu (redovi sa sva tri ulaza): jedan model {mae_pooled:.2f}, poseban po horizontu {mae_per_h:.2f}")
    for minutes in (30, 480):
        g = test[test["horizon_minutes"] == minutes]
        print(f"  MAE na {minutes} min: jedan model {_ols_mae(g, pooled):.2f}, poseban {_ols_mae(g, per_h[minutes]):.2f}")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    hours = table["horizont_min"] / 60
    for i, (feature, label) in enumerate(LINEAR_FEATURES.items()):
        color = LINEAR_COLORS[feature]
        ax.plot(hours, table[feature], color=color, linewidth=1.8, marker="o", markersize=3, label=label)
        ax.axhline(pooled[i + 1], color=color, linewidth=1, linestyle="--")
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.text(hours.iloc[-1], pooled[1], "isprekidano: jedan model\nza sve horizonte", ha="right", va="bottom",
            fontsize=8, color=INK)
    ax.set_xlabel("Horizont prognoze (h)", fontsize=9, color=MUTED)
    ax.set_ylabel("Koeficijent uz ulaz", fontsize=9, color=MUTED)
    _style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=3)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, "rad_4_5_linearni_koeficijenti.png")
    plt.close(fig)


FEATURE_NAMES_SR = {
    "y_t": "zauzetost sada", "y_t1": "zauzetost pre 30 min", "y_t2": "zauzetost pre 1 h",
    "delta": "promena za 30 min", "y_yesterday": "isto vreme juče", "y_lastweek": "isto vreme pre 7 dana",
    "hour": "doba dana", "dow": "dan u nedelji", "weekend": "vikend", "holiday": "praznik",
    "carpark": "parking", "capacity": "kapacitet", "horizon_minutes": "horizont",
}
# Sekvencijalna plava (kratki -> dugi horizonti), ista kao u ml/analyze_model.py.
HORIZON_GROUP_COLORS = ["#86b6ef", "#2a78d6", "#104281"]


def plot_shap_from_step5() -> None:
    """Slika 4.6: prosecan |SHAP| doprinos ulaza (ml/output/analiza_doprinos.csv,
    korak 5) - tacka po grupi horizonata, ulazi po ukupnom doprinosu."""
    import matplotlib.pyplot as plt

    table = pd.read_csv(os.path.join(OUTPUT_DIR, "analiza_doprinos.csv"))
    groups = list(dict.fromkeys(table["grupa_horizonata"]))  # redosled iz CSV-a: kratki, srednji, dugi
    wide = table.pivot(index="feature", columns="grupa_horizonata", values="doprinos_pp")[groups]
    wide = wide.loc[wide.mean(axis=1).sort_values().index]  # najvazniji gore
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.55))
    y = np.arange(len(wide))
    ax.hlines(y, wide.min(axis=1), wide.max(axis=1), color=GRID, linewidth=2, zorder=1)
    labels = {"do 2 h": "horizont do 2 h", "preko 8 h": "horizont preko 8 h"}
    for k, group in enumerate(groups):
        name = labels.get(group, "horizont od 2 do 8 h")
        ax.scatter(wide[group], y, color=HORIZON_GROUP_COLORS[k], s=28, zorder=2, label=name,
                   edgecolors="white", linewidths=0.6)
    ax.set_yticks(y, [FEATURE_NAMES_SR[f] for f in wide.index])
    ax.set_xlabel("Prosečan |SHAP| doprinos prognozi (p.p.)", fontsize=9, color=MUTED)
    ax.set_xlim(left=0)
    _style_axes(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", colors=INK)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    _save(fig, "rad_4_6_shap.png")
    plt.close(fig)


ABLATION_STYLE = {  # varijanta: (boja, marker, naziv u radu); "bez praznika" se ne crta - isto kao pun model
    "pun model": (INK, "o", "pun model"),
    "bez trenutnog stanja": ("#2a78d6", "s", "bez trenutnog stanja"),
    "bez istog termina ranije": ("#eb6834", "D", "bez istog vremena juče i pre 7 dana"),
    "samo kalendar i parking": ("#1baf7a", "^", "samo kalendar i parking"),
    "bez identiteta parkinga": ("#e87ba4", "v", "bez oznake parkinga i kapaciteta"),
}


def plot_ablation_from_step5() -> None:
    """Slika 4.7: MAE po horizontu za model bez pojedinih grupa ulaza
    (ml/output/analiza_ablacija_po_horizontu.csv, korak 5)."""
    import matplotlib.pyplot as plt

    table = pd.read_csv(os.path.join(OUTPUT_DIR, "analiza_ablacija_po_horizontu.csv"))
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.5))
    for variant, (color, marker, label) in ABLATION_STYLE.items():
        s = table[table["varijanta"] == variant]
        ax.plot(s["horizon_minutes"] / 60, s["MAE"], color=color, marker=marker, markersize=3.5,
                linewidth=2.2 if variant == "pun model" else 1.5, label=label, markevery=3)
    ax.set_xlabel("Horizont prognoze (h)", fontsize=9, color=MUTED)
    ax.set_ylabel("MAE na testu (p.p.)", fontsize=9, color=MUTED)
    ax.set_ylim(0, 8)
    _style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.8))
    _save(fig, "rad_4_7_ablacija.png")
    plt.close(fig)


CITY_CENTER = (52.6286, 1.2924)  # isto kao u ml/eval_recommender.py (okolina The Forum / pijace)
TYPE_STYLE = {"grad": ("#2a78d6", "o", "gradski parking"), "Park & Ride": ("#eb6834", "s", "Park & Ride"),
              "ostalo": ("#898781", "D", "ostalo (parking prodavnice)")}
SHORT_NAMES = {"Chantry Place (Chapelfield)": "Chantry Place", "Thickthorn Park & Ride": "Thickthorn",
               "Harford Park & Ride": "Harford", "Sprowston Park & Ride": "Sprowston", "Costessey Park & Ride": "Costessey",
               "Airport Park & Ride": "Airport", "Postwick Park & Ride": "Postwick", "B&Q Boundary Road": "B&Q"}


# Polozaj natpisa u centru (km, poravnanje), sa linijom do tacke - parkinzi su previse blizu za natpis pored tacke.
CENTER_LABELS = {
    "St Andrew's": (0.0, 0.62, "center"), "St Giles": (-0.5, 0.36, "right"), "The Forum": (-0.55, 0.0, "right"),
    "Chantry Place (Chapelfield)": (-0.42, -0.66, "center"), "Castle Quarter 1": (0.45, 0.3, "left"),
    "Rose Lane": (0.78, 0.06, "left"), "Castle Quarter 2": (0.6, -0.32, "left"), "John Lewis": (0.55, -0.66, "left"),
}


def _km_from_center(lat: float, lon: float) -> tuple[float, float]:
    """Polozaj u km istocno (x) i severno (y) od centra; dovoljno tacno za grad velicine Norwicha."""
    return ((lon - CITY_CENTER[1]) * 111.32 * np.cos(np.radians(CITY_CENTER[0])), (lat - CITY_CENTER[0]) * 111.32)


def park_table_and_map() -> None:
    """Tabela 6.2 (CSV) i slika 6.1: tip, kapacitet, prosecna zauzetost i polozaj parkinga."""
    import json

    import matplotlib.pyplot as plt

    meta = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "carparks_norfolk.json"),
                          encoding="utf-8"))["parks"]
    series = resample_per_park(load_raw("norfolk"))
    rows = []
    for p in meta:
        s = series[p["code"]].dropna()
        rows.append({"sifra": p["code"], "naziv": p["name"], "tip": p["type"], "kapacitet": p["capacity"],
                     "prosecna_zauzetost_pct": round(100 * s.mean(), 1), "dana_merenja": s.index.normalize().nunique(),
                     "x_km": _km_from_center(p["lat"], p["lon"])[0], "y_km": _km_from_center(p["lat"], p["lon"])[1]})
    table = pd.DataFrame(rows).sort_values(["tip", "naziv"], key=lambda c: c.map({"grad": 0, "Park & Ride": 1, "ostalo": 2})
                                           if c.name == "tip" else c)
    table.round(2).to_csv(os.path.join(OUTPUT_DIR, "rad_6_tabela_parkinga.csv"), index=False)
    print(table.drop(columns=["x_km", "y_km"]).to_string(index=False))

    fig, (ax_all, ax_center) = plt.subplots(1, 2, figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.5),
                                            gridspec_kw={"width_ratios": [1.15, 1]})
    for ax, (xlim, ylim), label_types in ((ax_all, ((-7.5, 7.5), (-7.5, 7.5)), {"Park & Ride", "ostalo"}),
                                          (ax_center, ((-1.15, 1.35), (-0.85, 0.8)), {"grad"})):
        if ax is ax_all:
            for ring in (2, 4, 6):
                ax.add_patch(plt.Circle((0, 0), ring, fill=False, color=GRID, linewidth=0.8))
                # oznaka prstena dole desno (tu nema parkinga)
                ax.text(ring * 0.72, -ring * 0.72, f"{ring} km", fontsize=7, color=MUTED, ha="left", va="top")
        for park_type, (color, marker, legend) in TYPE_STYLE.items():
            part = table[table["tip"] == park_type]
            ax.scatter(part["x_km"], part["y_km"], color=color, marker=marker, s=34, edgecolors="white",
                       linewidths=0.7, zorder=3, label=legend)
        for _, row in table.iterrows():
            if row["tip"] not in label_types:
                continue
            name = SHORT_NAMES.get(row["naziv"], row["naziv"])
            if ax is ax_center:
                tx, ty, ha = CENTER_LABELS[row["naziv"]]
                ax.annotate(name, (row["x_km"], row["y_km"]), xytext=(tx, ty), textcoords="data", fontsize=7,
                            color=INK, ha=ha, va="center",
                            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6, shrinkA=2, shrinkB=3))
            else:
                ax.annotate(name, (row["x_km"], row["y_km"]), xytext=(5, 3), textcoords="offset points", fontsize=7,
                            color=INK, ha="left", va="center")
        ax.plot(0, 0, marker="+", color=INK, markersize=9, zorder=4)
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_aspect("equal")
        _style_axes(ax)
        ax.grid(False)
        ax.set_xlabel("km istočno od centra", fontsize=8, color=MUTED)
    ax_all.set_ylabel("km severno od centra", fontsize=8, color=MUTED)
    ax_all.set_title("a) celo područje", fontsize=9, color=INK, loc="left")
    ax_center.set_title("b) centar (gradski parkinzi)", fontsize=9, color=INK, loc="left")
    handles, labels = ax_all.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=3)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    _save(fig, "rad_6_1_lokacije.png")
    plt.close(fig)


COPIED_TUESDAYS = ["2017-10-10", "2017-10-17", "2017-10-24"]


def plot_copied_weeks() -> None:
    """Slika 6.2: tri uzastopna utorka na B&Q Boundary Road (podaci su kopija
    prethodne nedelje) i na The Forum (stvarna merenja), zauzetost na 30 min."""
    import matplotlib.pyplot as plt

    series = resample_per_park(load_raw("norfolk"))
    shades = ["#86b6ef", "#2a78d6", "#104281"]  # sekvencijalna plava: tri uzastopne nedelje
    fig, axes = plt.subplots(1, 2, figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.42), sharey=True)
    for ax, (code, title) in zip(axes, (("C06391", "a) B&Q Boundary Road"), ("CPN0009", "b) The Forum"))):
        for day, color in zip(COPIED_TUESDAYS, shades):
            d = series[code][day]
            d = d[(d.index.hour >= 8) & (d.index.hour < 23)]
            t = pd.Timestamp(day)
            label = f"utorak {t.day}.{t.month}.{t.year}."
            ax.plot(d.index.hour + d.index.minute / 60, d * 100, color=color, linewidth=1.6, label=label)
        ax.set_title(title, fontsize=9, color=INK, loc="left")
        ax.set_xlabel("Sat", fontsize=8, color=MUTED)
        ax.set_xticks([8, 11, 14, 17, 20, 23])
        _style_axes(ax)
    axes[0].set_ylabel("Zauzetost (%)", fontsize=8, color=MUTED)
    axes[0].set_ylim(0, 100)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=3)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    _save(fig, "rad_6_2_kopirane_nedelje.png")
    plt.close(fig)


# Poredjenje modela: ista validirana paleta kao u ml/compare_models.py; referentne prognoze sive.
MODEL_STYLE = {
    "XGBoost": ("#2a78d6", "o", "-", "XGBoost"),
    "HistGradientBoosting": ("#1baf7a", "D", "-", "HistGradientBoosting"),
    "Random Forest": ("#e87ba4", "v", "-", "Random Forest"),
    "Ridge": ("#eda100", "s", "-", "Ridge"),
    "pre nedelju dana": ("#898781", "s", "--", "pravilo: pre nedelju dana"),
    "tipicna kriva": ("#898781", "x", "-.", "prosečan profil"),
}


def plot_model_comparison() -> None:
    """Slika 7.1: MAE po horizontu za sve modele i referentne prognoze (korak 4,
    ml/output/poredjenje_modela_po_horizontu.csv). "Poslednja vrednost" nije na
    slici, jer raste do ~34 p.p. i spljostila bi razlike medju modelima."""
    import matplotlib.pyplot as plt

    table = pd.read_csv(os.path.join(OUTPUT_DIR, "poredjenje_modela_po_horizontu.csv"))
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.5))
    for model, (color, marker, style, label) in MODEL_STYLE.items():
        s = table[table["model"] == model]
        ax.plot(s["horizon_minutes"] / 60, s["MAE"], color=color, marker=marker, markersize=3.5, markevery=3,
                linestyle=style, linewidth=2.2 if model == "XGBoost" else 1.4, label=label)
    ax.set_xlabel("Horizont prognoze (h)", fontsize=9, color=MUTED)
    ax.set_ylabel("MAE na testu (p.p.)", fontsize=9, color=MUTED)
    ax.set_ylim(0, 10)
    _style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=3)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    _save(fig, "rad_7_1_poredjenje_modela.png")
    plt.close(fig)


def plot_errors() -> None:
    """Slika 7.2: a) MAE po satu cilja za gradske i P&R parkinge, b) MAE po stvarnoj
    popunjenosti (korak 5, analiza_greska_po_satu.csv i _po_popunjenosti.csv).
    B&Q (tip "ostalo") nije prikazan, jer su mu podaci velikim delom kopirani."""
    import matplotlib.pyplot as plt

    by_hour = pd.read_csv(os.path.join(OUTPUT_DIR, "analiza_greska_po_satu.csv"))
    by_band = pd.read_csv(os.path.join(OUTPUT_DIR, "analiza_greska_po_popunjenosti.csv"))
    fig, (ax_h, ax_b) = plt.subplots(1, 2, figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.42),
                                     gridspec_kw={"width_ratios": [1.5, 1]})
    for column, label in (("grad", "gradski parkinzi"), ("Park & Ride", "Park & Ride")):
        ax_h.plot(by_hour["sat"], by_hour[column], color=COLORS[column], marker="o", markersize=3, linewidth=1.8,
                  label=label)
    ax_h.set_xticks([8, 11, 14, 17, 20, 23])
    ax_h.set_xlabel("Sat ciljnog trenutka", fontsize=8, color=MUTED)
    ax_h.set_ylabel("MAE (p.p.)", fontsize=8, color=MUTED)
    ax_h.set_title("a) po dobu dana", fontsize=9, color=INK, loc="left")
    ax_h.set_ylim(0, 10)
    ax_h.legend(frameon=False, fontsize=8, loc="upper left")
    bars = ax_b.bar(range(len(by_band)), by_band["MAE"], color=COLORS["grad"], width=0.6)
    for bar, (_, row) in zip(bars, by_band.iterrows()):
        ax_b.annotate(f"{row['MAE']:.1f}".replace(".", ","), (bar.get_x() + bar.get_width() / 2, row["MAE"]),
                      xytext=(0, 2), textcoords="offset points", ha="center", fontsize=8, color=INK)
    ax_b.set_xticks(range(len(by_band)), by_band["pun"])
    ax_b.set_xlabel("Stvarna popunjenost", fontsize=8, color=MUTED)
    ax_b.set_title("b) po popunjenosti", fontsize=9, color=INK, loc="left")
    ax_b.set_ylim(0, 10)
    for ax in (ax_h, ax_b):
        _style_axes(ax)
    fig.tight_layout()
    _save(fig, "rad_7_2_greske.png")
    plt.close(fig)


CITY_ORDER = ["norfolk", "birmingham", "glasgow", "nottingham"]
CITY_LABEL = {"norfolk": "Norwich (Norfolk)", "birmingham": "Birmingham", "glasgow": "Glasgow", "nottingham": "Nottingham"}
CITY_STYLE = {"norfolk": ("#2a78d6", "o"), "birmingham": ("#eda100", "s"), "glasgow": ("#1baf7a", "D"),
              "nottingham": ("#e87ba4", "v")}


def plot_cities() -> None:
    """Slike 7.3 i 7.4 iz rezultata koraka 7 (gradovi_po_horizontu.csv, gradovi_tacnost.csv)."""
    import matplotlib.pyplot as plt

    horizons = pd.read_csv(os.path.join(OUTPUT_DIR, "gradovi_po_horizontu.csv"))
    own = horizons[(horizons["varijanta"] == "sopstveni") & (horizons["n"] >= 500)]
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    for city in CITY_ORDER:
        s = own[own["grad"] == city]
        color, marker = CITY_STYLE[city]
        ax.plot(s["horizon_minutes"] / 60, s["mae"], color=color, marker=marker, markersize=3, markevery=3,
                linewidth=1.8, label=CITY_LABEL[city])
    ax.set_xlabel("Horizont prognoze (h)", fontsize=9, color=MUTED)
    ax.set_ylabel("MAE na testu (p.p.)", fontsize=9, color=MUTED)
    ax.set_ylim(0, 8)
    _style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=4)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    _save(fig, "rad_7_3_gradovi.png")
    plt.close(fig)

    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "gradovi_tacnost.csv")).set_index("grad").loc[CITY_ORDER]
    variants = [("sopstveni_mae", "#2a78d6", "sopstveni model grada"),
                ("sopstveni_bez_id_mae", "#1baf7a", "sopstveni, bez oznake parkinga"),
                ("prenos_norfolk_mae", "#eda100", "Norfolk model, bez ponovnog učenja"),
                ("pre_nedelju_mae", "#898781", "pravilo: pre nedelju dana")]
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.45))
    width = 0.2
    x = np.arange(len(summary))
    for k, (column, color, label) in enumerate(variants):
        values = summary[column].to_numpy(dtype=float)
        bars = ax.bar(x + (k - 1.5) * width, np.nan_to_num(values), width * 0.92, color=color, label=label,
                      edgecolor="white", linewidth=0.8)
        for bar, value in zip(bars, values):
            if not np.isnan(value):
                ax.annotate(f"{value:.1f}".replace(".", ","), (bar.get_x() + bar.get_width() / 2, value),
                            xytext=(0, 2), textcoords="offset points", ha="center", fontsize=7, color=INK)
    ax.set_xticks(x, [CITY_LABEL[c] for c in summary.index])
    ax.set_ylabel("MAE na testu (p.p.)", fontsize=9, color=MUTED)
    ax.set_ylim(0, 10.5)
    _style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    _save(fig, "rad_7_4_prenos.png")
    plt.close(fig)


def plot_score_parts() -> None:
    """Slika 8.1: sema tri dela skora preporuke (backend/recommender.py). Vreme voznje
    meri deo puta od polaska do parkinga, blizina deo od parkinga do cilja, a
    dostupnost se predvidja za trenutak dolaska na parking."""
    import matplotlib.pyplot as plt

    drive, goal, avail = "#2a78d6", "#1baf7a", "#eb6834"  # validirana paleta
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.36))
    start, park, dest = (0.0, 0.0), (6.0, 0.0), (9.4, 0.0)
    ax.annotate("", xy=(park[0] - 0.35, 0), xytext=(start[0] + 0.3, 0),
                arrowprops={"arrowstyle": "-|>", "color": drive, "lw": 2.2})
    ax.annotate("", xy=(dest[0] - 0.3, 0), xytext=(park[0] + 0.35, 0),
                arrowprops={"arrowstyle": "-|>", "color": goal, "lw": 2.2, "linestyle": (0, (4, 2))})
    ax.plot(*start, marker="o", markersize=11, color=MUTED)
    ax.plot(*park, marker="s", markersize=19, color=avail)
    ax.text(*park, "P", ha="center", va="center", fontsize=10, color="white", fontweight="bold")
    ax.plot(*dest, marker="*", markersize=17, color=INK)
    for (x, _), label in ((start, "polazak"), (park, "parking"), (dest, "cilj")):
        ax.text(x, -0.34, label, ha="center", va="top", fontsize=9, color=INK)

    ax.text(3.0, 0.22, "vožnja od polaska do parkinga", ha="center", fontsize=8.5, color=INK)
    ax.text(3.0, -0.78, "vreme vožnje V (trošak, ponder $w_3$)\n$V$ = min(1, vreme vožnje / 30 min)",
            ha="center", va="top", fontsize=8, color=MUTED)
    ax.text(7.7, 0.22, "do cilja: peške,\nsa P&R autobusom", ha="center", fontsize=8.5, color=INK)
    ax.text(7.7, -0.78, "blizina cilju B (ponder $w_2$)\n$B$ = max(0, 1 − udaljenost / 10 km)",
            ha="center", va="top", fontsize=8, color=MUTED)
    ax.text(park[0], 0.9, "dostupnost pri dolasku D (ponder $w_1$)\n$D$ = 1 − predviđena zauzetost u trenutku dolaska",
            ha="center", fontsize=8, color=MUTED)
    ax.annotate("", xy=(park[0], 0.32), xytext=(park[0], 0.86), arrowprops={"arrowstyle": "-", "color": avail, "lw": 1})
    ax.set_xlim(-0.8, 10.2)
    ax.set_ylim(-1.3, 1.35)
    ax.axis("off")
    fig.tight_layout()
    _save(fig, "rad_8_1_delovi_skora.png")
    plt.close(fig)


def _comma(value: float, _pos=None) -> str:
    return f"{value:g}".replace(".", ",")


def plot_weight_selection() -> None:
    """Slika 8.2: izbor pondera na validacionom periodu (oktobar 2017), iz rezultata
    koraka 6b (izbor_pondera.csv, izbor_pondera_pareto.csv): a) svih 231 kombinacija i
    Pareto front, b) uvecan ravan deo oko izabrane kombinacije."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter

    table = pd.read_csv(os.path.join(OUTPUT_DIR, "izbor_pondera.csv"))
    front = pd.read_csv(os.path.join(OUTPUT_DIR, "izbor_pondera_pareto.csv")).sort_values("vreme_do_cilja_min")

    def row(w1, w2):
        return table[np.isclose(table["w1"], w1) & np.isclose(table["w2"], w2)].iloc[0]

    chosen, hand, zero_risk = row(0.15, 0.40), row(0.55, 0.30), row(0.45, 0.35)
    blue, orange, gray = "#2a78d6", "#eb6834", "#898781"
    tolerance = table["pun_95_pct"].min() + 0.5
    zoom = (19.4, 22.7, -0.12, 1.3)

    fig, (ax_all, ax_zoom) = plt.subplots(1, 2, figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.5),
                                          gridspec_kw={"width_ratios": [1.15, 1]})
    for ax in (ax_all, ax_zoom):
        ax.scatter(table["vreme_do_cilja_min"], table["pun_95_pct"], s=9, color=gray, alpha=0.45, linewidths=0,
                   label="sve kombinacije (231)")
        ax.plot(front["vreme_do_cilja_min"], front["pun_95_pct"], color=blue, linewidth=1.6, marker="o",
                markersize=2.8, label="Pareto front")
        ax.scatter([hand["vreme_do_cilja_min"]], [hand["pun_95_pct"]], s=40, marker="s", color=orange, zorder=4,
                   edgecolors="white", linewidths=1, label="ručno izabrani ponderi")
        ax.scatter([chosen["vreme_do_cilja_min"]], [chosen["pun_95_pct"]], s=60, marker="D", color=blue, zorder=5,
                   edgecolors="white", linewidths=1.2, label="izabrano pravilom")
        ax.axhline(tolerance, color=MUTED, linestyle=":", linewidth=1, label="dozvoljen rizik (najmanji + 0,5 p.p.)")
        ax.set_xlabel("Prosečno vreme od polaska do cilja (min)", fontsize=8.5, color=MUTED)
        ax.yaxis.set_major_formatter(FuncFormatter(_comma))
        ax.xaxis.set_major_formatter(FuncFormatter(_comma))
        _style_axes(ax)
    ax_all.set_ylabel("Dolazak na pun parking (% vožnji)", fontsize=8.5, color=MUTED)
    ax_all.add_patch(Rectangle((zoom[0], zoom[2]), zoom[1] - zoom[0], zoom[3] - zoom[2], fill=False,
                               edgecolor=INK, linewidth=0.8, linestyle="--"))
    ax_all.set_title("a) sve kombinacije", fontsize=9, color=INK, loc="left")
    ax_zoom.set_title("b) uvećana oblast oko izabrane", fontsize=9, color=INK, loc="left")
    ax_zoom.set_xlim(zoom[0], zoom[1])
    ax_zoom.set_ylim(zoom[2], zoom[3])
    # natpisi pondera (w1 / w2 / w3) u praznom gornjem delu, sa linijom do tacke
    for point, text, xy_text, align in ((chosen, "0,15 / 0,40 / 0,45", (19.5, 1.05), "left"),
                                        (zero_risk, "0,45 / 0,35 / 0,20", (21.0, 0.8), "center"),
                                        (hand, "0,55 / 0,30 / 0,15", (22.65, 1.05), "right")):
        ax_zoom.annotate(text, (point["vreme_do_cilja_min"], point["pun_95_pct"]), xytext=xy_text,
                         fontsize=7.5, color=INK, ha=align, va="bottom",
                         arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.7, "shrinkA": 0})
    handles, labels = ax_all.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper center", ncol=3)
    fig.tight_layout(rect=(0, 0, 1, 0.85))
    _save(fig, "rad_8_2_izbor_pondera.png")
    plt.close(fig)


def plot_architecture() -> None:
    """Slika 9.1: arhitektura sistema - priprema i ucenje (offline), backend i frontend."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    offline, backend, frontend = "#eb6834", "#2a78d6", "#1baf7a"  # validirana paleta
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.66))
    panels = (((0.1, 3.7), offline, "Priprema i učenje (offline)"), ((4.1, 7.9), backend, "Backend (Python, FastAPI)"),
              ((8.3, 11.9), frontend, "Frontend (Next.js, Leaflet)"))
    for (x0, x1), color, title in panels:
        ax.add_patch(FancyBboxPatch((x0, 0.35), x1 - x0, 7.15, boxstyle="round,pad=0,rounding_size=0.25",
                                    facecolor=color, alpha=0.07, edgecolor=color, linewidth=1.2))
        ax.text((x0 + x1) / 2, 7.2, title, ha="center", va="center", fontsize=8.5, color=INK, fontweight="bold")

    def box(x, y, text, color, w=3.1, h=0.95, dashed=False):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.12",
                                    facecolor="white", edgecolor=color, linewidth=1.3,
                                    linestyle=(0, (3, 2)) if dashed else "-"))
        ax.text(x, y, text, ha="center", va="center", fontsize=7.5, color=INK, linespacing=1.3)

    def arrow(xy_from, xy_to, label=None, label_xy=None, ha="center"):
        ax.annotate("", xy=xy_to, xytext=xy_from, arrowprops={"arrowstyle": "-|>", "color": MUTED, "lw": 1.1,
                                                             "shrinkA": 0, "shrinkB": 0})
        if label:
            ax.text(*label_xy, label, ha=ha, va="center", fontsize=6.8, color=MUTED, linespacing=1.2)

    lx, mx, rx = 1.9, 6.0, 10.1
    box(lx, 6.2, "Norfolk.csv\n(istorijska merenja)", offline)
    box(lx, 4.7, "priprema podataka i učenje\n(data_prep.py,\ntrain_norfolk.py)", offline, h=1.2)
    box(lx, 3.2, "naučeni model\n(model_norfolk.joblib)", offline)
    box(lx, 1.5, "evaluacija i izbor pondera\n(eval_recommender.py,\nselect_weights.py)", offline, h=1.25)
    arrow((lx, 5.72), (lx, 5.3))
    arrow((lx, 4.1), (lx, 3.68), "trening pre\n1.10.2017", (lx + 0.15, 3.89), ha="left")

    box(mx, 6.2, "ReplaySource\n(merenja samo do „sada”)", backend)
    box(mx, 4.95, "SimulationClock\n(sat, korak 30 min)", backend)
    box(mx, 3.7, "Predictor\n(ulazi iz prošlosti, prognoza)", backend)
    box(mx, 2.45, "Recommender\n(skor, rangiranje)", backend)
    box(mx, 1.2, "REST API (main.py)", backend, h=0.75)
    arrow((lx + 1.55, 6.2), (mx - 1.55, 6.2), "isti\npodaci", (3.95, 6.62))
    for y_top, y_bottom in ((5.72, 5.43), (4.47, 4.18), (3.22, 2.93), (1.97, 1.58)):
        arrow((mx, y_top), (mx, y_bottom))
    arrow((lx + 1.55, 3.2), (mx - 1.55, 3.55))
    ax.text(3.9, 3.05, "model", ha="center", fontsize=6.8, color=MUTED)
    arrow((lx + 1.55, 1.5), (mx - 1.55, 2.3), "iste\nfunkcije", (3.8, 2.6))

    box(rx, 6.2, "OSRM (javni servis)\nruta za prikaz na mapi", frontend, dashed=True)
    box(rx, 4.7, "mapa sa zauzetošću\n(markeri, ruta, legenda)", frontend)
    box(rx, 3.45, "top preporuke\n(delovi skora)", frontend)
    box(rx, 2.2, "predikcija naspram\nstvarnosti (demo)", frontend)
    arrow((rx, 5.72), (rx, 5.18))
    ax.annotate("", xy=(rx - 1.55, 1.2), xytext=(mx + 1.55, 1.2),
                arrowprops={"arrowstyle": "<|-|>", "color": MUTED, "lw": 1.1, "shrinkA": 0, "shrinkB": 0})
    ax.text(8.15, 1.45, "JSON,\nna 3 s", ha="center", va="bottom", fontsize=6.8, color=MUTED, linespacing=1.2)
    ax.plot([rx - 1.55, rx - 1.75, rx - 1.75], [1.2, 1.2, 4.7], color=MUTED, lw=1.1)
    for y in (4.7, 3.45, 2.2):
        ax.plot([rx - 1.75, rx - 1.55], [y, y], color=MUTED, lw=1.1)

    ax.set_xlim(0, 12)
    ax.set_ylim(0.2, 7.6)
    ax.axis("off")
    fig.tight_layout(pad=0.2)
    _save(fig, "rad_9_1_arhitektura.png")
    plt.close(fig)


def tree_figures() -> None:
    from ml.data_prep import prepare_multi_horizon_dataset

    train, test = prepare_multi_horizon_dataset("norfolk")
    plot_small_tree(train)
    plot_tree_depth(train, test)
    plot_forest_size(train, test)
    plot_boosting_rounds(train, test)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plot_supervised_example()
    plot_data_split()
    tree_figures()
    types = {p["park_id"]: p["type"] for p in parks_module.load_parks()}
    series = {k: s[s.index < TRAIN_END] for k, s in resample_per_park(load_raw("norfolk")).items()}

    plot_week(series, types)

    max_lag = MAX_LAG_DAYS * STEPS_PER_DAY
    acf_by_type: dict[str, list[np.ndarray]] = {}
    for park_id, s in series.items():
        if park_id in EXCLUDED_FROM_ACF or types[park_id] not in COLORS:
            continue
        acf_by_type.setdefault(types[park_id], []).append(autocorrelation(s, max_lag))
    # nanmean: za neke pomake (npr. 12 h kod P&R, koji nocu ne radi) parking nema nijedan par merenja.
    mean_acf = {t: np.nanmean(v, axis=0) for t, v in acf_by_type.items()}
    plot_autocorrelation(mean_acf)

    print("\nAutokorelacija (prosek po tipu parkinga):")
    for park_type, acf in mean_acf.items():
        at = {name: acf[steps - 1] for name, steps in
              (("30 min", 1), ("2 h", 4), ("12 h", 24), ("1 dan", 48), ("3 dana", 144), ("7 dana", 336), ("14 dana", 672))}
        print(f"  {park_type} ({len(acf_by_type[park_type])} parkinga): " + ", ".join(f"{k} {v:.2f}" for k, v in at.items()))


if __name__ == "__main__":
    main()
