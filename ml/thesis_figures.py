"""
Slike za pisani rad (korak 9) koje ne pravi nijedan od eksperimenata.

Poglavlje 3.1 (vremenske serije):
  rad_3_1_nedeljni_tok.png      zauzetost gradskog i P&R parkinga kroz jednu nedelju
  rad_3_2_autokorelacija.png    autokorelacija zauzetosti za pomake do dve nedelje

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
    fig, ax = plt.subplots(figsize=(8, 3.6))
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

    fig, ax = plt.subplots(figsize=(8, 3.6))
    for park_type, acf in acf_by_type.items():
        lags_days = np.arange(1, len(acf) + 1) / STEPS_PER_DAY
        label = "gradski parkinzi" if park_type == "grad" else "Park & Ride parkinzi"
        ax.plot(lags_days, acf, color=COLORS[park_type], linewidth=1.6, label=label)
    for day, text in ((1, "1 dan: isto vreme juče"), (7, "7 dana: isto vreme pre nedelju dana")):
        ax.axvline(day, color=MUTED, linewidth=0.9, linestyle=":")
        ax.annotate(text, (day, 1.08), xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.set_xticks(range(0, MAX_LAG_DAYS + 1))
    ax.set_xlim(0, MAX_LAG_DAYS)
    ax.set_ylim(-0.6, 1.35)  # prostor iznad krivih za natpise i legendu
    ax.set_yticks([-0.5, 0, 0.5, 1.0])
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xlabel("Pomak (dani)", fontsize=9, color=MUTED)
    ax.set_ylabel("Autokorelacija", fontsize=9, color=MUTED)
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, loc="upper right", ncol=2)
    fig.tight_layout()
    _save(fig, "rad_3_2_autokorelacija.png")
    plt.close(fig)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
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
