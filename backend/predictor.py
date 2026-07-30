"""
Predictor - ucitava ml/model.joblib pri startu i daje predikciju OccupancyRate
za dati parking i vreme.
"""

import os

import joblib
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "model.joblib")

DAY_NAME_TO_NUM = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_bundle = joblib.load(MODEL_PATH)
_model = _bundle["model"]
_park_encoder = _bundle["park_encoder"]
_features = _bundle["features"]


def known_park_ids() -> set:
    return set(_park_encoder.classes_)


def parse_day(day) -> int:
    """Prihvata dan kao broj (0=pon..6=ned) ili ime (Mon, tue, WED, ...)."""
    if isinstance(day, int) or (isinstance(day, str) and day.strip().isdigit()):
        return int(day)
    key = str(day).strip().lower()[:3]
    if key not in DAY_NAME_TO_NUM:
        raise ValueError(f"Nepoznat dan: {day!r} (ocekivano Mon..Sun ili 0..6)")
    return DAY_NAME_TO_NUM[key]


def predict_occupancy_rate(park_id: str, hour: int, minute: int, day, capacity: float) -> float:
    if park_id not in known_park_ids():
        raise ValueError(f"Nepoznat park_id: {park_id}")

    day_num = parse_day(day)
    park_encoded = _park_encoder.transform([park_id])[0]

    row = pd.DataFrame(
        [
            {
                "Hour": hour,
                "Minute": minute,
                "DayOfWeekNum": day_num,
                "ParkEncoded": park_encoded,
                "Capacity": capacity,
            }
        ]
    )[_features]

    prediction = float(_model.predict(row)[0])
    return min(max(prediction, 0.0), 100.0)
