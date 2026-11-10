"""
Spisak Norfolk parkinga - kapacitet se cita iz data/raw/Norfolk.csv (stvaran
podatak), koordinate/ime/tip iz data/carparks_norfolk.json (poglavlje 5,
MASTER_PLAN.md). Imena i koordinate svih 15 parkinga su iz zvanicnog Norfolk
County Council feeda (arhiviran 2018, vidi _comment u JSON-u). Parking bez
koordinata (lat/lng = None, confirmed = False) se i dalje ne prikazuje na mapi
niti ulazi u preporuku - ne izmisljaju se koordinate.
"""

import json
import os
from functools import lru_cache

from ml.data_prep import DEFAULT_CITY, load_raw

COORDINATES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "carparks_norfolk.json")

with open(COORDINATES_PATH, encoding="utf-8") as f:
    _coords_config = json.load(f)

_COORDS_BY_CODE = {entry["code"]: entry for entry in _coords_config["parks"]}


@lru_cache(maxsize=None)
def _capacities(city: str) -> dict[str, int]:
    """Kapacitet po parkingu, procitan iz CSV-a jednom po gradu. Ranije se CSV citao
    na svaki API zahtev (~0,5 s); istorijski podaci se ne menjaju, pa se cuvaju."""
    df = load_raw(city)
    return {park_id: int(c) for park_id, c in df.groupby("SystemCodeNumber")["Capacity"].first().items()}


def load_parks(city: str = DEFAULT_CITY) -> list[dict]:
    parks = []
    for park_id, capacity in _capacities(city).items():
        meta = _COORDS_BY_CODE.get(park_id, {})
        parks.append(
            {
                "park_id": park_id,
                "name": meta.get("name"),
                "capacity": capacity,
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
