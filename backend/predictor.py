"""
Predictor (redizajnirano 2026-10-17) - gradi feature red za simulirano "sada"
i BILO KOJI horizont (u koracima od 30 min), koristi jedan
ml/model_norfolk.joblib kome je horizont obicna ulazna promenljiva
(`horizon_minutes`) - vidi ml/data_prep.py i PROGRESS.md za razlog izmene
(profesor nije trazio fiksna tri horizonta, samo "sta god je moguce").

Feature-i su racunati iz apsolutnog vremena (now, target_time) - pogodno za
predikciju jedne tacke u svakom simulacionom tick-u.
"""

from __future__ import annotations

import os

import joblib
import numpy as np
import pandas as pd

from ml.data_prep import HOLIDAYS, MAX_HORIZON_STEPS

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "model_norfolk.joblib")

_bundle = joblib.load(MODEL_PATH)
_model = _bundle["model"]
_FEATURES = _bundle["features"]
_CARPARK_CATEGORIES = _bundle["carpark_categories"]
_HORIZON_STEPS_RANGE = _bundle.get("horizon_steps_range", list(range(1, MAX_HORIZON_STEPS + 1)))
_MAX_HORIZON_STEPS = max(_HORIZON_STEPS_RANGE)
_MIN_HORIZON_STEPS = min(_HORIZON_STEPS_RANGE)


def carpark_categories() -> list[str]:
    return _CARPARK_CATEGORIES


def max_horizon_steps() -> int:
    return _MAX_HORIZON_STEPS


def _lookup(history: pd.Series, time: pd.Timestamp) -> float:
    return history.get(time, np.nan)


def build_feature_row(
    history: pd.Series,
    now: pd.Timestamp,
    horizon_steps: int,
    park_id: str,
    capacity: float,
    carpark_categories: list[str],
) -> pd.DataFrame:
    target_time = now + pd.Timedelta(minutes=30 * horizon_steps)

    y_t = _lookup(history, now)
    y_t1 = _lookup(history, now - pd.Timedelta(minutes=30))

    row = {
        "y_t": y_t,
        "y_t1": y_t1,
        "y_t2": _lookup(history, now - pd.Timedelta(minutes=60)),
        "delta": y_t - y_t1,
        "y_yesterday": _lookup(history, target_time - pd.Timedelta(days=1)),
        "y_lastweek": _lookup(history, target_time - pd.Timedelta(days=7)),
        "hour": target_time.hour + target_time.minute / 60,
        "dow": target_time.dayofweek,
        "weekend": int(target_time.dayofweek >= 5),
        "holiday": int(target_time.normalize() in HOLIDAYS),
        "carpark": park_id,
        "capacity": capacity,
        "horizon_minutes": 30 * horizon_steps,
    }
    frame = pd.DataFrame([row])
    frame["carpark"] = pd.Categorical(frame["carpark"], categories=carpark_categories)
    return frame[_FEATURES]


def predict_rate(
    history: pd.Series,
    now: pd.Timestamp,
    horizon_steps: int,
    park_id: str,
    capacity: float,
    carpark_categories: list[str] | None = None,
) -> float | None:
    """Predvidjena stopa zauzetosti (0-1) za dati horizont (u koracima od 30
    min, 1..MAX_HORIZON_STEPS), ili None ako nema trenutnog ocitavanja (rupa u
    podacima - nema smisla predvidjati) ili je horizont van treniranog opsega."""
    if not (_MIN_HORIZON_STEPS <= horizon_steps <= _MAX_HORIZON_STEPS):
        raise ValueError(
            f"Horizont van treniranog opsega: {horizon_steps} koraka "
            f"(dozvoljeno {_MIN_HORIZON_STEPS}-{_MAX_HORIZON_STEPS})"
        )
    if pd.isna(_lookup(history, now)):
        return None

    categories = carpark_categories or _CARPARK_CATEGORIES
    row = build_feature_row(history, now, horizon_steps, park_id, capacity, categories)
    return float(np.clip(_model.predict(row)[0], 0, 1))
