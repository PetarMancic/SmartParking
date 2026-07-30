"""
Faza 3 - FastAPI backend.

Endpointi:
- GET /parks   - lista svih parkinga (id, kapacitet, koordinate)
- GET /predict - predvidjena popunjenost za dati parking i vreme
- GET /recommend - rangirana lista parkinga za datu destinaciju i vreme

Rangiranje za /recommend (ponderisani skor, saobracaj kao TODO) zivi u
backend/recommender.py - namerno odvojeno od predikcije, po CLAUDE.md.
"""

from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend import parks as parks_module
from backend import predictor
from backend import recommender

app = FastAPI(title="Smart Parking Recommendation API")

# Frontend (Next.js dev server) radi na drugom portu - PoC, pa dozvoljavamo samo njega.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/parks")
def get_parks():
    return parks_module.load_parks()


@app.get("/predict")
def predict(park_id: str, hour: int, day: str):
    park = parks_module.get_park(park_id)
    if park is None:
        raise HTTPException(status_code=404, detail=f"Nepoznat park_id: {park_id}")

    try:
        occupancy_rate = predictor.predict_occupancy_rate(
            park_id=park_id, hour=hour, minute=0, day=day, capacity=park["capacity"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "park_id": park_id,
        "hour": hour,
        "day": day,
        "predicted_occupancy_rate": round(occupancy_rate, 2),
        "predicted_available_spots": round(park["capacity"] * (1 - occupancy_rate / 100)),
        "availability_score": round(1 - occupancy_rate / 100, 4),
    }


@app.get("/predict_current")
def predict_current(park_id: str | None = None, hour: int | None = None, day: str | None = None):
    now = datetime.now()
    if hour is None:
        hour = now.hour
    if day is None:
        day = now.strftime("%a")

    if park_id is not None:
        park = parks_module.get_park(park_id)
        if park is None:
            raise HTTPException(status_code=404, detail=f"Nepoznat park_id: {park_id}")

        occupancy_rate = predictor.predict_occupancy_rate(
            park_id=park_id,
            hour=hour,
            minute=0,
            day=day,
            capacity=park["capacity"],
        )
        return {
            "park_id": park_id,
            "hour": hour,
            "day": day,
            "predicted_occupancy_rate": round(occupancy_rate, 2),
            "predicted_available_spots": round(park["capacity"] * (1 - occupancy_rate / 100)),
            "availability_score": round(1 - occupancy_rate / 100, 4),
        }

    parks = parks_module.load_parks()
    results = []
    for park in parks:
        occupancy_rate = predictor.predict_occupancy_rate(
            park_id=park["park_id"],
            hour=hour,
            minute=0,
            day=day,
            capacity=park["capacity"],
        )
        results.append(
            {
                "park_id": park["park_id"],
                "capacity": park["capacity"],
                "predicted_occupancy_rate": round(occupancy_rate, 2),
                "predicted_available_spots": round(park["capacity"] * (1 - occupancy_rate / 100)),
                "availability_score": round(1 - occupancy_rate / 100, 4),
            }
        )

    results.sort(key=lambda item: item["availability_score"], reverse=True)
    return {
        "hour": hour,
        "day": day,
        "parks": results,
    }


@app.get("/recommend")
def recommend(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    hour: int,
    day: str,
    top_n: int = 5,
    radius: float | None = None,
):
    return recommender.recommend_parks(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        hour=hour,
        day=day,
        top_n=top_n,
        radius_meters=radius,
    )
