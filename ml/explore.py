"""
Faza 1 - Priprema podataka i EDA.

Ucitava data/parking.csv, parsira vreme, izvlaci vremenske feature-e
i crta dnevnu krivu punjenja (OccupancyRate kroz sat u danu) za par parkinga.
"""

import os

import matplotlib.pyplot as plt
import pandas as pd

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "parking.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Parkinzi za koje crtamo dnevnu krivu (nekoliko reprezentativnih primera)
SAMPLE_PARKS = ["BHMBCCMKT01", "Broad Street", "BHMEURBRD01", "Bull Ring"]


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"])
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df["Hour"] = df["LastUpdated"].dt.hour
    df["Minute"] = df["LastUpdated"].dt.minute
    df["DayOfWeekNum"] = df["LastUpdated"].dt.dayofweek  # 0 = ponedeljak
    df["IsWeekend"] = df["DayOfWeekNum"].isin([5, 6])
    return df


def print_basic_stats(df: pd.DataFrame) -> None:
    print("=== Osnovne informacije o datasetu ===")
    print(f"Broj redova: {len(df)}")
    print(f"Broj razlicitih parkinga: {df['SystemCodeNumber'].nunique()}")
    print(f"Period merenja: {df['LastUpdated'].min()} -> {df['LastUpdated'].max()}")
    print()

    print("=== Statistika OccupancyRate (%) ===")
    print(df["OccupancyRate"].describe())
    print()

    print("=== Statistika Capacity po parkingu ===")
    print(df.groupby("SystemCodeNumber")["Capacity"].first().describe())
    print()

    print("=== Prosecna popunjenost po danu u nedelji ===")
    print(df.groupby("DayOfWeek")["OccupancyRate"].mean().sort_values(ascending=False))
    print()

    print("=== Prosecna popunjenost: radni dan vs. vikend ===")
    print(df.groupby("IsWeekend")["OccupancyRate"].mean())
    print()


def plot_daily_curves(df: pd.DataFrame) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    available_parks = [p for p in SAMPLE_PARKS if p in df["SystemCodeNumber"].unique()]
    if not available_parks:
        # fallback: uzmi prve par parkinga koji stvarno postoje u datasetu
        available_parks = list(df["SystemCodeNumber"].unique()[:4])

    fig, ax = plt.subplots(figsize=(10, 6))
    for park in available_parks:
        park_df = df[df["SystemCodeNumber"] == park]
        hourly_avg = park_df.groupby("Hour")["OccupancyRate"].mean()
        ax.plot(hourly_avg.index, hourly_avg.values, marker="o", label=park)

    ax.set_xlabel("Sat u danu")
    ax.set_ylabel("Prosecna popunjenost (%)")
    ax.set_title("Dnevna kriva punjenja parkinga")
    ax.legend()
    ax.grid(True, alpha=0.3)

    output_path = os.path.join(OUTPUT_DIR, "daily_curve.png")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Grafik sacuvan: {output_path}")


def main() -> None:
    df = load_data()
    df = add_time_features(df)
    print_basic_stats(df)
    plot_daily_curves(df)


if __name__ == "__main__":
    main()
