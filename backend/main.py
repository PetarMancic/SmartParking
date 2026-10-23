"""
Faza 3 (master rad) - FastAPI backend za Norfolk + pseudo real-time simulator.

Endpointi:
- GET  /parks              - lista Norfolk parkinga (koordinate, kapacitet, tip)
- GET  /simulation/state   - simulirano vreme, da li sat radi, brzina
- POST /simulation/start   - pokrece sat (opciono: start_time, speed)
- POST /simulation/pause   - pauzira sat
- POST /simulation/speed   - menja brzinu (factor = sim-minuta po stvarnoj sekundi)
- GET  /state              - trenutna zauzetost + (opciono) zauzetost za bilo koji target_time
- GET  /history            - tipicna kriva za dan u nedelji (iz treninga) + stvarni tok danas
- GET  /recommend          - rangirana lista parkinga za destinaciju

Simulator (backend/simulator.py) reprodukuje Norfolk CSV hronoloskim redom
(backend/datasource.py - ReplaySource): model u trenutku t vidi samo podatke
do t (poglavlje 7, MASTER_PLAN.md). Predikcija (backend/predictor.py) i
preporuka (backend/recommender.py) su odvojeni moduli, po CLAUDE.md principu.
"""

import os

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend import parks as parks_module
from backend import predictor
from backend import recommender
from backend.datasource import ReplaySource
from backend.simulator import SimulationClock
from ml.data_prep import CITY_CONFIGS

app = FastAPI(title="Smart Parking Recommendation API - Norfolk")

# Frontend (Next.js dev server) radi na drugom portu - PoC, pa dozvoljavamo samo njega.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

CITY = "norfolk"
# Pocetak test perioda (podaci koje model nije video pri treningu) - poglavlje 7.
DEFAULT_START_TIME = pd.Timestamp("2017-10-01 08:00:00")

_data_source = ReplaySource(city=CITY)
_clock = SimulationClock(_data_source, start_time=DEFAULT_START_TIME)
_carpark_categories = predictor.carpark_categories()

_MAE_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "output", f"{CITY}_mae_po_parkingu.csv")
_mae_df = pd.read_csv(_MAE_PATH, index_col=0) if os.path.exists(_MAE_PATH) else None
if _mae_df is not None:
    _mae_df.columns = _mae_df.columns.astype(int)  # horizon u minutima


def _mae_for(park_id: str, horizon_minutes: int) -> float | None:
    if _mae_df is None or park_id not in _mae_df.index or horizon_minutes not in _mae_df.columns:
        return None
    value = _mae_df.loc[park_id, horizon_minutes]
    return None if pd.isna(value) else float(value)


@app.get("/parks")
def get_parks():
    return parks_module.load_parks(CITY)


@app.get("/simulation/state")
def simulation_state():
    return _clock.state()


@app.post("/simulation/start")
async def simulation_start(start_time: str | None = None, speed: float | None = None):
    # async def - mora da radi na event loop thread-u, posto SimulationClock.start()
    # zove asyncio.create_task() (zahteva aktivan loop u trenutnom thread-u).
    if start_time is not None:
        try:
            _clock.reset(pd.Timestamp(start_time))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"Neispravno start_time: {exc}")
    if speed is not None:
        try:
            _clock.set_speed(speed)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    _clock.start()
    return _clock.state()


@app.post("/simulation/pause")
async def simulation_pause():
    _clock.pause()
    return _clock.state()


@app.post("/simulation/speed")
async def simulation_speed(factor: float):
    try:
        _clock.set_speed(factor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _clock.state()


def _park_state(park_id: str, capacity: float, now: pd.Timestamp, target_time: pd.Timestamp | None) -> dict:
    history = _data_source.history_until(park_id, now)
    current_rate = history.get(now)
    has_current_reading = not pd.isna(current_rate)

    result = {
        "park_id": park_id,
        "current_occupancy_rate": round(float(current_rate) * 100, 2) if has_current_reading else None,
        "current_available_spots": round(capacity * (1 - float(current_rate))) if has_current_reading else None,
        "target_time": None,
        "target_occupancy_rate": None,
        "target_available_spots": None,
        "is_prediction": None,
        "horizon_minutes": None,
        "horizon_clamped": False,
        "mae": None,
    }

    if target_time is None:
        return result

    result["target_time"] = target_time.isoformat()
    diff_minutes = (target_time - now).total_seconds() / 60

    if diff_minutes <= 0:
        # Trazeno vreme je sada ili u proslosti - to je vec poznato (izmereno),
        # nema predikcije.
        rate = history.get(target_time)
        result["is_prediction"] = False
        if not pd.isna(rate):
            result["target_occupancy_rate"] = round(float(rate) * 100, 2)
            result["target_available_spots"] = round(capacity * (1 - float(rate)))
        return result

    horizon_steps = max(1, round(diff_minutes / 30))
    max_steps = predictor.max_horizon_steps()
    if horizon_steps > max_steps:
        result["horizon_clamped"] = True
        horizon_steps = max_steps

    rate = predictor.predict_rate(history, now, horizon_steps, park_id, capacity, _carpark_categories)
    result["is_prediction"] = True
    result["horizon_minutes"] = horizon_steps * 30
    result["mae"] = _mae_for(park_id, horizon_steps * 30)
    if rate is not None:
        result["target_occupancy_rate"] = round(rate * 100, 2)
        result["target_available_spots"] = round(capacity * (1 - rate))

    return result


@app.get("/state")
def state(park_id: str | None = None, target_time: str | None = None):
    now = _clock.current_time

    parsed_target = None
    if target_time is not None:
        try:
            parsed_target = pd.Timestamp(target_time)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"Neispravno target_time: {exc}")

    if park_id is not None:
        park = parks_module.get_park(park_id, CITY)
        if park is None:
            raise HTTPException(status_code=404, detail=f"Nepoznat park_id: {park_id}")
        return {"current_time": now.isoformat(), "park": _park_state(park_id, park["capacity"], now, parsed_target)}

    parks = parks_module.load_parks(CITY)
    results = [_park_state(p["park_id"], p["capacity"], now, parsed_target) for p in parks]
    return {"current_time": now.isoformat(), "parks": results}


def _typical_curve(park_id: str, dow: int) -> list[dict]:
    """Prosecna zauzetost po 30-min slotu za dati dan u nedelji, racunato samo
    iz trening perioda (pre pocetka test perioda) - poglavlje 6, MASTER_PLAN.md."""
    test_start = CITY_CONFIGS[CITY]["test_start"]
    series = _data_source.training_series(park_id, test_start)
    frame = series.rename("rate").to_frame()
    frame = frame[frame.index.dayofweek == dow]
    frame["time"] = frame.index.strftime("%H:%M")
    avg = frame.groupby("time")["rate"].mean().sort_index()
    return [
        {"time": t, "avg_occupancy_rate": None if pd.isna(v) else round(float(v) * 100, 2)}
        for t, v in avg.items()
    ]


def _actual_today(park_id: str, now: pd.Timestamp) -> list[dict]:
    """Stvarna ocitavanja od ponoci simuliranog dana do 'sada' (inkluzivno)."""
    history = _data_source.history_until(park_id, now)
    today = history[history.index >= now.normalize()]
    return [
        {"time": t.isoformat(), "occupancy_rate": None if pd.isna(v) else round(float(v) * 100, 2)}
        for t, v in today.items()
    ]


@app.get("/history")
def history(park_id: str):
    park = parks_module.get_park(park_id, CITY)
    if park is None:
        raise HTTPException(status_code=404, detail=f"Nepoznat park_id: {park_id}")

    now = _clock.current_time
    return {
        "park_id": park_id,
        "current_time": now.isoformat(),
        "day_of_week": now.strftime("%a"),
        "typical_curve": _typical_curve(park_id, now.dayofweek),
        "actual_today": _actual_today(park_id, now),
    }


@app.get("/recommend")
def recommend(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    top_n: int = 5,
    radius: float | None = None,
    departure_time: str | None = None,
):
    parsed_departure = None
    if departure_time is not None:
        try:
            parsed_departure = pd.Timestamp(departure_time)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"Neispravno departure_time: {exc}")

    return recommender.recommend_parks(
        data_source=_data_source,
        clock=_clock,
        carpark_categories=_carpark_categories,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        top_n=top_n,
        radius_meters=radius,
        departure_time=parsed_departure,
    )
