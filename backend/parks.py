"""
Koordinate i kapacitet parkinga.

NAPOMENA O KOORDINATAMA: dataset (data/parking.csv) ne sadrzi geografske
koordinate. Koordinate ispod su RUCNO DODELJENE / FIKTIVNE priblizne lokacije
rasporedjene oko centra Birminghama (52.4796, -1.8998) - koriste se samo za
demo mapu i racunanje udaljenosti u ovom PoC-u, ne predstavljaju stvarne GPS
pozicije ovih parkinga. Kapacitet se cita direktno iz dataseta (stvaran podatak).
"""

import os

import pandas as pd

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "parking.csv")

DEFAULT_COORDINATES = (52.4796, -1.8998)

FICTIONAL_COORDINATES = {
    "BHMBCCMKT01": (52.4804, -1.8933),
    "BHMBCCPST01": (52.4780, -1.8990),
    "BHMBCCSNH01": (52.4823, -1.8952),
    "BHMBCCTHL01": (52.4771, -1.9057),
    "BHMBRCBRG01": (52.4842, -1.9105),
    "BHMBRCBRG02": (52.4851, -1.9080),
    "BHMBRCBRG03": (52.4860, -1.9130),
    "BHMBRTARC01": (52.4715, -1.8975),
    "BHMEURBRD01": (52.4794, -1.9151),
    "BHMEURBRD02": (52.4805, -1.9170),
    "BHMMBMMBX01": (52.4750, -1.8890),
    "BHMNCPHST01": (52.4788, -1.8940),
    "BHMNCPLDH01": (52.4835, -1.9010),
    "BHMNCPNHS01": (52.4762, -1.9105),
    "BHMNCPNST01": (52.4700, -1.9050),
    "BHMNCPPLS01": (52.4869, -1.8955),
    "BHMNCPRAN01": (52.4726, -1.9130),
    "Broad Street": (52.4778, -1.9160),
    "Bull Ring": (52.4772, -1.8931),
    "NIA Car Parks": (52.4802, -1.9143),
    "NIA South": (52.4790, -1.9155),
    "Others-CCCPS105a": (52.4740, -1.9020),
    "Others-CCCPS119a": (52.4855, -1.9040),
    "Others-CCCPS133": (52.4695, -1.8960),
    "Others-CCCPS135a": (52.4810, -1.8870),
    "Others-CCCPS202": (52.4884, -1.9095),
    "Others-CCCPS8": (52.4670, -1.9000),
    "Others-CCCPS98": (52.4746, -1.8865),
    "Shopping": (52.4780, -1.8925),
}


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
