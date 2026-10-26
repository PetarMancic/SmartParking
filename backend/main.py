"""
Faza 3 (master rad) - FastAPI backend za Norfolk + pseudo real-time simulator.

Endpointi:
- GET  /parks              - lista Norfolk parkinga (koordinate, kapacitet, tip)
- GET  /simulation/state   - simulirano vreme, da li sat radi, brzina
- POST /simulation/start   - pokrece sat (opciono: start_time, speed)
- POST /simulation/pause   - pauzira sat
- POST /simulation/reset   - skok na izabrani trenutak test perioda (sat ostaje pauziran)
- POST /simulation/speed   - menja brzinu (factor = sim-minuta po stvarnoj sekundi)
- GET  /state              - trenutna zauzetost + (opciono) zauzetost za bilo koji target_time
- GET  /history            - tipicna kriva za dan u nedelji (iz treninga) + stvarni tok danas
- GET  /recommend          - rangirana lista parkinga za destinaciju
- GET  /compare            - retrospektivno poredjenje predikcije i stvarnosti za jedan dan

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
TEST_START = CITY_CONFIGS[CITY]["test_start"]
TEST_END = CITY_CONFIGS[CITY]["test_end"]  # ekskluzivno

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


def _simulation_state() -> dict:
    # Granice test perioda idu uz stanje sata - frontend po njima ogranicava
    # izbor datuma (demo samo nad podacima koje model nije video pri treningu).
    return {
        **_clock.state(),
        "test_start": TEST_START.isoformat(),
        "test_end": TEST_END.isoformat(),
    }


@app.get("/simulation/state")
def simulation_state():
    return _simulation_state()


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
    return _simulation_state()


@app.post("/simulation/pause")
async def simulation_pause():
    _clock.pause()
    return _simulation_state()


@app.post("/simulation/speed")
async def simulation_speed(factor: float):
    try:
        _clock.set_speed(factor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _simulation_state()


@app.post("/simulation/reset")
async def simulation_reset(start_time: str):
    # Skok na izabrani trenutak (demo: "pokazi mi subotu 14.10. u 10h").
    # Zaokruzuje se na 30-min mrezu i dozvoljava samo test period.
    try:
        parsed = pd.Timestamp(start_time).floor("30min")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Neispravno start_time: {exc}")
    if not (TEST_START <= parsed < TEST_END):
        raise HTTPException(status_code=400, detail="start_time mora biti u test periodu.")
    _clock.reset(parsed)
    return _simulation_state()


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


def _rate_pct(value) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value) * 100, 2)


def _mae_pp(pairs: list[tuple[float | None, float | None]]) -> float | None:
    """MAE u procentnim poenima nad parovima (predikcija, stvarno) gde postoje oba."""
    errors = [abs(p - a) for p, a in pairs if p is not None and a is not None]
    return round(sum(errors) / len(errors), 2) if errors else None


ROLLING_HORIZON_STEPS = 2  # "uvek sat unapred" linija


@app.get("/compare")
def compare(park_id: str, date: str, from_time: str = "10:00"):
    """Retrospektivno poredjenje za odbranu/demo: sta je model predvideo, a sta
    se stvarno desilo tog dana. Namerno vidi ceo dan (i "buducnost" u odnosu
    na from_time) - zato je odvojeno od zivog simulatora (/state), koji
    buducnost nikad ne vidi. Same predikcije i dalje koriste samo podatke do
    svog trenutka predvidjanja (predictor.predict_rates).

    - forecast: predikcija napravljena u `from_time` za svaki kasniji slot dana
    - rolling_1h: za svaki slot, predikcija napravljena sat ranije
    - typical: prosek za taj dan u nedelji iz trening perioda (bez modela)
    """
    park = parks_module.get_park(park_id, CITY)
    if park is None:
        raise HTTPException(status_code=404, detail=f"Nepoznat park_id: {park_id}")
    try:
        day_start = pd.Timestamp(date).normalize()
        from_ts = (day_start + pd.Timedelta(from_time + ":00")).floor("30min")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Neispravan datum/vreme: {exc}")
    if not (TEST_START <= day_start < TEST_END):
        raise HTTPException(status_code=400, detail="Datum mora biti u test periodu (podaci koje model nije video).")

    slots = pd.date_range(day_start, periods=48, freq="30min")
    history = _data_source.history_until(park_id, slots[-1])
    actual = [_rate_pct(history.get(t)) for t in slots]

    later_slots = [t for t in slots if t > from_ts]
    forecast_steps = [round((t - from_ts) / pd.Timedelta(minutes=30)) for t in later_slots]
    forecast_raw = predictor.predict_rates(
        history, [(from_ts, k) for k in forecast_steps], park_id, park["capacity"], _carpark_categories
    )
    forecast_by_time = {t: _rate_pct(v) for t, v in zip(later_slots, forecast_raw)}

    rolling_raw = predictor.predict_rates(
        history,
        [(t - pd.Timedelta(minutes=30 * ROLLING_HORIZON_STEPS), ROLLING_HORIZON_STEPS) for t in slots],
        park_id,
        park["capacity"],
        _carpark_categories,
    )
    rolling = [_rate_pct(v) for v in rolling_raw]

    typical = [p["avg_occupancy_rate"] for p in _typical_curve(park_id, day_start.dayofweek)]
    typical = (typical + [None] * 48)[:48]

    points = [
        {
            "time": t.isoformat(),
            "actual": actual[i],
            "forecast": forecast_by_time.get(t),
            "rolling_1h": rolling[i],
            "typical": typical[i],
        }
        for i, t in enumerate(slots)
    ]
    after = [p for p in points if pd.Timestamp(p["time"]) > from_ts]

    return {
        "park_id": park_id,
        "name": park["name"],
        "date": day_start.date().isoformat(),
        "day_of_week": day_start.strftime("%a"),
        "from_time": from_ts.isoformat(),
        "has_reading_at_from_time": not pd.isna(history.get(from_ts)),
        "points": points,
        "mae": {
            "forecast": _mae_pp([(p["forecast"], p["actual"]) for p in after]),
            "typical_same_slots": _mae_pp([(p["typical"], p["actual"]) for p in after if p["forecast"] is not None]),
            "rolling_1h": _mae_pp([(p["rolling_1h"], p["actual"]) for p in points]),
        },
    }
