"""
Koordinate i kapacitet parkinga.

NAPOMENA O KOORDINATAMA: dataset (data/parking.csv) ne sadrzi geografske
koordinate. Koordinate su RUCNO DODELJENE / FIKTIVNE priblizne lokacije
rasporedjene oko centra Birminghama, ucitane iz data/park_coordinates.json
(konfiguracija, ne hardkodovano u kodu) - koriste se samo za demo mapu i
racunanje udaljenosti u ovom PoC-u, ne predstavljaju stvarne GPS pozicije
ovih parkinga. Kapacitet se cita direktno iz dataseta (stvaran podatak).
"""

import json
import os

import pandas as pd

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "parking.csv")
COORDINATES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "park_coordinates.json")

with open(COORDINATES_PATH, encoding="utf-8") as f:
    _coordinates_config = json.load(f)

DEFAULT_COORDINATES = tuple(_coordinates_config["default"])
FICTIONAL_COORDINATES = {park_id: tuple(coords) for park_id, coords in _coordinates_config["parks"].items()}


def load_parks() -> list[dict]:
    df = pd.read_csv(DATA_PATH)
    capacities = df.groupby("SystemCodeNumber")["Capacity"].first()

    parks = []
    for park_id, capacity in capacities.items():
        lat, lng = FICTIONAL_COORDINATES.get(park_id, DEFAULT_COORDINATES)
        parks.append(
            {
                "park_id": park_id,
                "capacity": int(capacity),
                "lat": lat,
                "lng": lng,
            }
        )
    return parks


def get_park(park_id: str) -> dict | None:
    for park in load_parks():
        if park["park_id"] == park_id:
            return park
    return None

