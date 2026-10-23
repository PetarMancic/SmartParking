"""
Spisak Norfolk parkinga - kapacitet se cita iz data/raw/Norfolk.csv (stvaran
podatak), koordinate/ime/tip iz data/carparks_norfolk.json (poglavlje 5,
MASTER_PLAN.md). Neuparene sifre imaju lat/lng = None i confirmed = False -
ne izmisljaju se koordinate.
"""

import json
import os

from ml.data_prep import DEFAULT_CITY, load_raw

COORDINATES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "carparks_norfolk.json")

with open(COORDINATES_PATH, encoding="utf-8") as f:
    _coords_config = json.load(f)

_COORDS_BY_CODE = {entry["code"]: entry for entry in _coords_config["parks"]}


def load_parks(city: str = DEFAULT_CITY) -> list[dict]:
    df = load_raw(city)
    capacities = df.groupby("SystemCodeNumber")["Capacity"].first()

    parks = []
    for park_id, capacity in capacities.items():
        meta = _COORDS_BY_CODE.get(park_id, {})
        parks.append(
            {
                "park_id": park_id,
                "name": meta.get("name"),
                "capacity": int(capacity),
                "lat": meta.get("lat"),
                "lng": meta.get("lon"),
                "type": meta.get("type"),
                "confirmed": meta.get("confirmed", False),
            }
        )
    return parks


def get_park(park_id: str, city: str = DEFAULT_CITY) -> dict | None:
    for park in load_parks(city):
        if park["park_id"] == park_id:
            return park
    return None
