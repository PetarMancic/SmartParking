"""
Simulacioni sat (poglavlje 7, MASTER_PLAN.md).

Reprodukuje istoriju hronoloskim redom uz podesivu brzinu. Tick je 30
simuliranih minuta; podrazumevana brzina je 2 sim-minuta po stvarnoj sekundi
(tick traje 15 stvarnih sekundi) - brzo za demo, dovoljno sporo da se prati.
"""

from __future__ import annotations

import asyncio

import pandas as pd

from backend.datasource import DataSource

TICK_MINUTES = 30
DEFAULT_SPEED = 2.0  # sim-minuta po stvarnoj sekundi


class SimulationClock:
    def __init__(self, data_source: DataSource, start_time: pd.Timestamp, speed: float = DEFAULT_SPEED):
        self.data_source = data_source
        self.current_time = start_time
        self.speed = speed
        self.running = False
        self._task: asyncio.Task | None = None

    @property
    def tick_seconds(self) -> float:
        return TICK_MINUTES / self.speed

    def state(self) -> dict:
        grid_start, grid_end = self.data_source.grid_bounds()
        return {
            "current_time": self.current_time.isoformat(),
            "running": self.running,
            "speed_minutes_per_second": self.speed,
            "tick_minutes": TICK_MINUTES,
            "grid_start": grid_start.isoformat(),
            "grid_end": grid_end.isoformat(),
        }

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("Brzina mora biti pozitivan broj.")
        self.speed = speed

    def reset(self, start_time: pd.Timestamp) -> None:
        self.pause()
        self.current_time = start_time

    def advance_once(self) -> None:
        _, grid_end = self.data_source.grid_bounds()
        next_time = self.current_time + pd.Timedelta(minutes=TICK_MINUTES)
        if next_time > grid_end:
            self.current_time = grid_end
            self.pause()
            return
        self.current_time = next_time

    async def _run(self) -> None:
        try:
            while self.running:
                await asyncio.sleep(self.tick_seconds)
                if not self.running:
                    break
                self.advance_once()
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run())

    def pause(self) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
