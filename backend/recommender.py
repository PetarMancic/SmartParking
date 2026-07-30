"""
Faza 4 - Modul za preporuku parkinga.

Rangira parkinge po ponderisanom skoru:

    skor = w1 * predvidjena_dostupnost + w2 * blizina_destinaciji - w3 * saobracaj

Ovo NIJE ML zadatak - obicno ponderisano rangiranje, namerno odvojeno od
predikcije (backend/predictor.py), po principu iz CLAUDE.md.
"""

import math

from backend import parks as parks_module
from backend import predictor

# Ponderi - konstante, lako izmenljive radi eksperimentisanja.
W1_PREDICTED_AVAILABILITY = 0.55
W2_PROXIMITY = 0.3
W3_TRAFFIC = 0.15

# Traffic density je simuliran kao jednostavan signal na osnovu udaljenosti
# od destinacije i trenutnog sata. U master radu ovo se zamenjuje stvarnim
# podacima o saobracaju ili eksternim API-jem.

TOP_N_DEFAULT = 5


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def _traffic_density_score(distance_km: float, hour: int) -> float:
    peak_hour_penalty = 0.0
    if 7 <= hour <= 9 or 16 <= hour <= 19:
        peak_hour_penalty = 0.25

    proximity_penalty = min(0.35, distance_km / 10.0)
    return min(1.0, peak_hour_penalty + proximity_penalty)


def recommend_parks(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    hour: int,
    day,
    top_n: int = TOP_N_DEFAULT,
    radius_meters: float | None = None,
) -> list[dict]:
    all_parks = parks_module.load_parks()
    candidates = []

    for park in all_parks:
        distance_to_origin_km = _haversine_km(origin_lat, origin_lng, park["lat"], park["lng"])
        distance_to_destination_km = _haversine_km(dest_lat, dest_lng, park["lat"], park["lng"])

        if radius_meters is not None:
            radius_km = radius_meters / 1000.0
            if distance_to_destination_km > radius_km:
                continue

        try:
            occupancy_rate = predictor.predict_occupancy_rate(
                park_id=park["park_id"], hour=hour, minute=0, day=day, capacity=park["capacity"]
            )
        except ValueError:
            continue

        candidates.append(
            {
                "park_id": park["park_id"],
                "lat": park["lat"],
                "lng": park["lng"],
                "predicted_occupancy_rate": round(occupancy_rate, 2),
                "availability_score": round(1 - occupancy_rate / 100, 4),
                "distance_to_origin_km": round(distance_to_origin_km, 2),
                "distance_to_destination_km": round(distance_to_destination_km, 2),
            }
        )

    if not candidates:
        return []

    max_drive_distance_km = max(candidate["distance_to_origin_km"] for candidate in candidates) or 1.0

    results = []
    for candidate in candidates:
        predicted_availability = 1 - candidate["predicted_occupancy_rate"] / 100
        closeness = 1 - (candidate["distance_to_origin_km"] / max_drive_distance_km)
        traffic = _traffic_density_score(candidate["distance_to_destination_km"], hour)

        score = (
            W1_PREDICTED_AVAILABILITY * predicted_availability
            + W2_PROXIMITY * closeness
            - W3_TRAFFIC * traffic
        )

        results.append(
            {
                "park_id": candidate["park_id"],
                "lat": candidate["lat"],
                "lng": candidate["lng"],
                "predicted_occupancy_rate": candidate["predicted_occupancy_rate"],
                "availability_score": candidate["availability_score"],
                "distance_to_origin_km": candidate["distance_to_origin_km"],
                "distance_to_destination_km": candidate["distance_to_destination_km"],
                "distance_km": candidate["distance_to_destination_km"],
                "score": round(score, 4),
                "score_components": {
                    "predicted_availability": round(predicted_availability, 4),
                    "closeness": round(closeness, 4),
                    "traffic": traffic,
                    "weights": {
                        "w1_predicted_availability": W1_PREDICTED_AVAILABILITY,
                        "w2_proximity": W2_PROXIMITY,
                        "w3_traffic": W3_TRAFFIC,
                    },
                },
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]
