"""
Priprema podataka za trening modela zauzetosti (poglavlje 3, MASTER_PLAN.md).

Logika feature-a je ista kao u reference/norfolk_xgb_eksperiment.py, ovde
uopstena po gradu (CITY_CONFIGS) tako da je izbor skupa podataka konfigurabilan.
Aplikacija koristi Norfolk. Birmingham, Glasgow i Nottingham sluze samo za
proveru modela u drugim gradovima (korak 7, ml/other_cities.py); za njih nema
koordinata, pa ni preporuke. Upotrebljivi parkinzi i periodi su iz
MASTER_PLAN.md (poglavlje 3, "Ostali gradovi"), a test je poslednja ~2 meseca
upotrebljivog perioda, kao kod Norfolka.

CSV fajlovi su van ovog repoa, u data/raw/ na nivou celog master projekta
(C:\\FAX\\MASTER\\SIR1\\data\\raw), zajednicki za sve faze skalabilnosti.
"""

import os

import pandas as pd

SLOT = "30min"
STEPS_PER_DAY = 48  # koraka od 30 min u danu

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_DATA_RAW_DIR = os.path.join(_PROJECT_ROOT, "data", "raw")

CITY_CONFIGS = {
    "norfolk": {
        "csv_path": os.path.join(_DATA_RAW_DIR, "Norfolk.csv"),
        "excluded_parks": {"CPN0001", "CPN0002", "CPN0010"},
        "test_start": pd.Timestamp("2017-10-01"),
        "test_end": pd.Timestamp("2017-12-06"),
    },
    # Merenja ~08:00-16:30 na 30 min; rupa 12.-19.2.2017.
    "birmingham": {
        "csv_path": os.path.join(_DATA_RAW_DIR, "Birmingham.csv"),
        "excluded_parks": {"BHMAPCARC01", "NIA North", "NIA West"},
        "test_start": pd.Timestamp("2017-03-01"),
        "test_end": pd.Timestamp("2017-04-29"),
    },
    # Merenja 0-24 h. Posle 7.8.2017 rupa do 29.11. - kasniji podaci se ne koriste.
    "glasgow": {
        "csv_path": os.path.join(_DATA_RAW_DIR, "Glasgow.csv"),
        "excluded_parks": {"CPG04C", "CPG05C", "CPG11C"},
        "period_end": pd.Timestamp("2017-08-08"),
        "test_start": pd.Timestamp("2017-06-01"),
        "test_end": pd.Timestamp("2017-08-08"),
    },
    # Merenja 0-24 h; rupa 16.5.-3.7.2017. Mnogo zaglavljenih senzora, pa se
    # zadrzava samo 11 upotrebljivih parkinga (included_parks).
    "nottingham": {
        "csv_path": os.path.join(_DATA_RAW_DIR, "Nottingham.csv"),
        "included_parks": {
            "211", "212", "C11001", "C11004", "C11005", "C11006",
            "FRSTPR", "PHNXPR", "PRLMNT", "RYLCT", "SB1-1",
        },
        "test_start": pd.Timestamp("2017-10-01"),
        "test_end": pd.Timestamp("2017-11-29"),
    },
}

DEFAULT_CITY = "norfolk"

# Praznici u Engleskoj u periodu podataka (vidi MASTER_PLAN.md, poglavlje 4).
HOLIDAYS = pd.to_datetime(
    [
        "2016-12-26", "2016-12-27", "2017-01-02", "2017-04-14", "2017-04-17",
        "2017-05-01", "2017-05-29", "2017-08-28",
    ]
)

# Imenovani horizonti - samo za prikaz/kratke precice (npr. "pogled" na mapi
# sa par brzih dugmadi). Model ume i za horizonte van ove liste - vidi
# MAX_HORIZON_STEPS ispod. 1 korak = 30 min.
HORIZONS = {"30 min": 1, "1 sat": 2, "2 sata": 4}

# Model predvidja za bilo koji horizont na 30-min mrezi, od 1 koraka do ovog
# maksimuma (30 koraka = 15h - pokriva ceo radni dan parkinga 08-23h). Profesor
# nije trazio fiksna tri horizonta (vidi MASTER_PLAN.md odluku od 2026-10-17,
# PROGRESS.md) - "sta god je moguce", pa horizont postaje obicna ulazna
# promenljiva umesto da se trenira poseban model po horizontu.
MAX_HORIZON_STEPS = 31
HORIZON_STEPS_RANGE = list(range(1, MAX_HORIZON_STEPS + 1))

FEATURES = [
    "y_t", "y_t1", "y_t2", "delta", "y_yesterday", "y_lastweek",
    "hour", "dow", "weekend", "holiday", "carpark", "capacity", "horizon_minutes",
]


def load_raw(city: str = DEFAULT_CITY) -> pd.DataFrame:
    """Ucitava sirovi CSV, izbacuje neupotrebljive parkinge, racuna stopu zauzetosti."""
    config = CITY_CONFIGS[city]
    df = pd.read_csv(config["csv_path"], dtype={"SystemCodeNumber": str})
    df = df[~df["SystemCodeNumber"].isin(config.get("excluded_parks", set()))]
    if "included_parks" in config:
        df = df[df["SystemCodeNumber"].isin(config["included_parks"])]
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"])
    if "period_end" in config:
        df = df[df["LastUpdated"] < config["period_end"]]
    df["rate"] = (df["Occupancy"] / df["Capacity"]).clip(0, 1)
    return df


def resample_per_park(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Resample na 30 min (srednja vrednost) po parkingu."""
    series = {}
    for park_id, g in df.groupby("SystemCodeNumber"):
        series[park_id] = g.set_index("LastUpdated")["rate"].resample(SLOT).mean()
    return series


def build_grid(series: dict[str, pd.Series]) -> pd.DatetimeIndex:
    """Pravilna mreza od 30 min preko celog perioda - shift(k) uvek znaci k*30min."""
    start = min(s.index.min() for s in series.values())
    end = max(s.index.max() for s in series.values())
    return pd.date_range(start, end, freq=SLOT)


def build_horizon_frame(
    series: dict[str, pd.Series],
    grid: pd.DatetimeIndex,
    capacities: pd.Series,
    horizon_steps: int,
) -> pd.DataFrame:
    """Gradi feature/target tabelu za dati horizont, za sve parkinge zajedno."""
    frames = []
    for park_id, s in series.items():
        y = s.reindex(grid)  # pravilna mreza -> shift(k) je tacan vremenski pomak
        f = pd.DataFrame(index=grid)
        f["target"] = y.shift(-horizon_steps)
        f["y_t"] = y
        f["y_t1"] = y.shift(1)
        f["y_t2"] = y.shift(2)
        f["delta"] = f["y_t"] - f["y_t1"]
        f["y_yesterday"] = y.shift(STEPS_PER_DAY - horizon_steps)
        f["y_lastweek"] = y.shift(7 * STEPS_PER_DAY - horizon_steps)
        target_time = grid + pd.Timedelta(minutes=30 * horizon_steps)
        f["target_time"] = target_time
        f["hour"] = target_time.hour + target_time.minute / 60
        f["dow"] = target_time.dayofweek
        f["weekend"] = (target_time.dayofweek >= 5).astype(int)
        f["holiday"] = target_time.normalize().isin(HOLIDAYS).astype(int)
        f["carpark"] = park_id
        f["capacity"] = capacities[park_id]
        f["horizon_minutes"] = 30 * horizon_steps
        frames.append(f)

    d = pd.concat(frames)
    # rupe se ne popunjavaju - izbacuju se samo redovi bez targeta ili bez trenutne vrednosti
    d = d.dropna(subset=["target", "y_t"])
    d["carpark"] = d["carpark"].astype("category")
    return d


def prepare_horizon_dataset(
    city: str, horizon_steps: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vraca (train_df, test_df) za JEDAN horizont, hronoloski podeljene po
    test_start/test_end grada."""
    config = CITY_CONFIGS[city]
    df = load_raw(city)
    capacities = df.groupby("SystemCodeNumber")["Capacity"].first()
    series = resample_per_park(df)
    grid = build_grid(series)
    d = build_horizon_frame(series, grid, capacities, horizon_steps)

    test = d[(d["target_time"] >= config["test_start"]) & (d["target_time"] < config["test_end"])]
    train = d[d["target_time"] < config["test_start"]]
    return train, test


def prepare_multi_horizon_dataset(
    city: str, horizon_steps_list: list[int] = HORIZON_STEPS_RANGE
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vraca (train_df, test_df) preko SVIH horizonata u listi, nadovezanih u
    jednu tabelu sa 'horizon_minutes' kao obicnom ulaznom promenljivom - za
    treniranje jednog modela koji ume da predvidi za bilo koji horizont iz liste
    (umesto posebnog modela po horizontu)."""
    config = CITY_CONFIGS[city]
    df = load_raw(city)
    capacities = df.groupby("SystemCodeNumber")["Capacity"].first()
    series = resample_per_park(df)
    grid = build_grid(series)

    train_frames, test_frames = [], []
    for horizon_steps in horizon_steps_list:
        d = build_horizon_frame(series, grid, capacities, horizon_steps)
        test = d[(d["target_time"] >= config["test_start"]) & (d["target_time"] < config["test_end"])]
        train = d[d["target_time"] < config["test_start"]]
        train_frames.append(train)
        test_frames.append(test)

    train_df = pd.concat(train_frames, ignore_index=True)
    test_df = pd.concat(test_frames, ignore_index=True)
    train_df["carpark"] = train_df["carpark"].astype("category")
    test_df["carpark"] = test_df["carpark"].astype("category")
    return train_df, test_df
