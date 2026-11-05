"""
Modul za preporuku parkinga (CLAUDE.md princip: predikcija i preporuka su
odvojeni moduli; preporuka je ponderisano rangiranje, NE ML).

    skor = w1 * predvidjena_dostupnost + w2 * blizina_destinaciji - w3 * vreme_voznje

`blizina_destinaciji` meri koliko vozac hoda od parkinga do cilja (ranije je
merila udaljenost od polaska, sto je moglo da preporuci parking blizu polaska
a daleko od cilja - promenjeno 2026-10-26, vidi PROGRESS.md).

`vreme_voznje` je procenjeno vreme voznje od polaska do parkinga, odnosno
trosak dolaska do parkinga. Zamenilo je heuristiku "saobracaj" (odluka mentora,
4.11.2026, vidi PROGRESS.md). Ta heuristika nije merila saobracaj: deo za vrsne
sate je bio isti za sve parkinge, a deo za udaljenost je kaznjavao udaljenost od
cilja, koju vec meri blizina. Dve komponente mere dva razlicita dela puta:
blizina deo od parkinga do cilja (peske), a vreme voznje deo od polaska do
parkinga (kolima). Zato sistem vise ne salje vozaca na parking na suprotnoj
strani grada. Podaci o saobracaju bi kasnije menjali samo procenu vremena
voznje (`eta_minutes`), a formula bi ostala ista.

Predikcija se radi za procenjeno vreme DOLASKA do parkinga, po poglavlju 6
MASTER_PLAN.md ("ako koristi zauzetost, treba da koristi predvidjenu
zauzetost za vreme dolaska"). Podrzan je i opcioni `departure_time` (npr.
vozac zna da krece u 17h, ne odmah) - tada se dolazak racuna od tog vremena,
ne od simuliranog "sada". Horizont je proizvoljan broj koraka od 30 min (ne
vise ograncen na 30min/1h/2h - vidi backend/predictor.py i PROGRESS.md), samo
ogranicen treniranim opsegom (predictor.max_horizon_steps()).
"""

from __future__ import annotations

import math

import pandas as pd

from backend import parks as parks_module
from backend import predictor
from backend.datasource import DataSource
from backend.simulator import SimulationClock

# Ponderi su izabrani na validacionom periodu (oktobar 2017) pravilom iz
# ml/select_weights.py: najmanje dolazaka na pun parking (tolerancija 0,5 p.p.),
# pa najkrace ukupno vreme od polaska do cilja. Do koraka 6b (5.11.2026) bili
# su rucno izabrani: 0.55 / 0.3 / 0.15. Ne menjati ih prema rezultatima sa
# novembra i decembra - na tim podacima se meri (ml/eval_recommender.py).
W1_PREDICTED_AVAILABILITY = 0.15
W2_PROXIMITY = 0.4
W3_DRIVE_TIME = 0.45

TOP_N_DEFAULT = 5

# Tipovi parkinga koji se preporucuju vozacu koji ide u grad. "ostalo" (B&Q
# Boundary Road - parking prodavnice za kupce, 3,6 km od centra, bez autobusa
# do centra) prikazuje se na mapi i ulazi u model, ali se ne preporucuje.
RECOMMENDABLE_TYPES = {"grad", "Park & Ride"}

# Fiksne skale za normalizaciju blizine i vremena voznje na 0-1 (korak 6b).
# Ranije se delilo najudaljenijim kandidatom u listi, pa su isti ponderi davali
# razlicit izbor izmedju dva ista parkinga u zavisnosti od toga koji su JOS
# parkinzi u listi (npr. filter "radius" izbaci P&R). U teoriji visekriterijumskog
# odlucivanja to je poznat problem relativne normalizacije ("rank reversal").
# Vrednosti su priblizno najvece udaljenosti u podrucju (najdalji P&R je ~7,4 km
# od centra, najduza voznja u simulaciji ~25-30 min); ponderi su birani za ove skale.
WALK_SCALE_KM = 10.0
DRIVE_SCALE_MIN = 30.0

# Nema ruting API-ja na backendu (frontend to radi preko OSRM-a za prikaz
# rute) - gruba procena vremena voznje po pravoj liniji. Koristi se za horizont
# predikcije (kada vozac stize) i za komponentu "vreme voznje" u skoru.
ASSUMED_DRIVE_SPEED_KMH = 30.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def _horizon_steps_for_arrival(now: pd.Timestamp, arrival_time: pd.Timestamp) -> int:
    """Horizont (koraci od 30 min) od simuliranog 'sada' do procenjenog
    dolaska, zaokruzen na mrezu i ogranicen na treniran opseg."""
    diff_minutes = (arrival_time - now).total_seconds() / 60
    steps = max(1, round(diff_minutes / 30))
    return min(steps, predictor.max_horizon_steps())


def recommend_parks(
    data_source: DataSource,
    clock: SimulationClock,
    carpark_categories: list[str],
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    top_n: int = TOP_N_DEFAULT,
    radius_meters: float | None = None,
    departure_time: pd.Timestamp | None = None,
) -> list[dict]:
    now = clock.current_time
    start_time = departure_time if departure_time is not None else now
    all_parks = parks_module.load_parks()
    candidates = []

    for park in all_parks:
        if park["lat"] is None or park["lng"] is None:
            continue  # nepotvrdjena lokacija - ne izmisljamo koordinate za preporuku
        if park["type"] not in RECOMMENDABLE_TYPES:
            continue

        distance_to_origin_km = _haversine_km(origin_lat, origin_lng, park["lat"], park["lng"])
        distance_to_destination_km = _haversine_km(dest_lat, dest_lng, park["lat"], park["lng"])

        if radius_meters is not None and distance_to_destination_km > radius_meters / 1000.0:
            continue

        eta_minutes = distance_to_origin_km / ASSUMED_DRIVE_SPEED_KMH * 60.0
        arrival_time = start_time + pd.Timedelta(minutes=eta_minutes)
        horizon_steps = _horizon_steps_for_arrival(now, arrival_time)

        history = data_source.history_until(park["park_id"], now)
        rate = predictor.predict_rate(history, now, horizon_steps, park["park_id"], park["capacity"], carpark_categories)
        if rate is None:
            continue

        candidates.append(
            {
                "park_id": park["park_id"],
                "lat": park["lat"],
                "lng": park["lng"],
                "eta_minutes": round(eta_minutes, 1),
                "horizon_minutes": horizon_steps * 30,
                "predicted_occupancy_rate": round(rate * 100, 2),
                "availability_score": round(1 - rate, 4),
                "distance_to_origin_km": round(distance_to_origin_km, 2),
                "distance_to_destination_km": round(distance_to_destination_km, 2),
            }
        )

    return score_candidates(candidates)[:top_n]


def score_candidates(
    candidates: list[dict],
    weights: tuple[float, float, float] = (W1_PREDICTED_AVAILABILITY, W2_PROXIMITY, W3_DRIVE_TIME),
) -> list[dict]:
    """Ponderisano rangiranje kandidata - cista funkcija (bez modela i sata),
    da bi je koristili i API (recommend_parks) i evaluacija
    (ml/eval_recommender.py). Svaki kandidat mora imati `availability_score`
    (0-1), `distance_to_destination_km` i `eta_minutes`. Vraca kandidate
    sortirane po skoru, od najboljeg.

    Blizina i vreme voznje su normalizovani na 0-1 fiksnim skalama
    (WALK_SCALE_KM, DRIVE_SCALE_MIN), a ne najudaljenijim kandidatom, pa
    poredjenje dva parkinga ne zavisi od toga koji su jos parkinzi u listi."""
    if not candidates:
        return []

    w1, w2, w3 = weights

    results = []
    for c in candidates:
        predicted_availability = c["availability_score"]
        closeness = max(0.0, 1 - c["distance_to_destination_km"] / WALK_SCALE_KM)
        drive_time = min(1.0, c["eta_minutes"] / DRIVE_SCALE_MIN)

        score = w1 * predicted_availability + w2 * closeness - w3 * drive_time

        results.append(
            {
                **c,
                "score": round(score, 4),
                "score_components": {
                    "predicted_availability": round(predicted_availability, 4),
                    "closeness": round(closeness, 4),
                    "drive_time": round(drive_time, 4),
                    "weights": {
                        "w1_predicted_availability": w1,
                        "w2_proximity": w2,
                        "w3_drive_time": w3,
                    },
                },
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
