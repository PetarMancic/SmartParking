"""
Izvor podataka za simulator (poglavlje 7, MASTER_PLAN.md).

DataSource je apstraktni interfejs iza kog stoji izvor zauzetosti parkinga.
ReplaySource simulira pseudo real-time reprodukcijom istorijskog CSV-a.
LiveSource je stub za buduce prave senzore/API.

Garancija koju svaka implementacija MORA da ispuni: history_until(park_id, until)
nikad ne vraca ocitavanje sa vremenom > until - model u trenutku t sme da vidi
samo podatke do t.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ml.data_prep import DEFAULT_CITY, build_grid, load_raw, resample_per_park


class DataSource(ABC):
    @abstractmethod
    def known_park_ids(self) -> set[str]: ...

    @abstractmethod
    def capacity(self, park_id: str) -> float: ...

    @abstractmethod
    def history_until(self, park_id: str, until: pd.Timestamp) -> pd.Series:
        """Zauzetost (rate, 0-1) na 30-min mrezi, do i ukljucujuci `until`."""

    @abstractmethod
    def grid_bounds(self) -> tuple[pd.Timestamp, pd.Timestamp]: ...


class ReplaySource(DataSource):
    """Reprodukuje istorijski CSV hronoloskim redom - cela serija je u memoriji,
    ali history_until nikad ne otkriva podatke posle datog trenutka."""

    def __init__(self, city: str = DEFAULT_CITY):
        self.city = city
        df = load_raw(city)
        self._capacities = df.groupby("SystemCodeNumber")["Capacity"].first()
        series = resample_per_park(df)
        self._grid = build_grid(series)
        self._series = {park_id: s.reindex(self._grid) for park_id, s in series.items()}

    def known_park_ids(self) -> set[str]:
        return set(self._series.keys())

    def capacity(self, park_id: str) -> float:
        return float(self._capacities[park_id])

    def history_until(self, park_id: str, until: pd.Timestamp) -> pd.Series:
        series = self._series[park_id]
        return series[series.index <= until]

    def training_series(self, park_id: str, before: pd.Timestamp) -> pd.Series:
        """Cela serija pre `before` (npr. pocetak test perioda) - koristi se samo
        za opisnu "tipicnu krivu" (poglavlje 6), nikad za predikciju uzivo."""
        series = self._series[park_id]
        return series[series.index < before]

    def grid_bounds(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self._grid[0], self._grid[-1]


class LiveSource(DataSource):
    """Stub za buduci pravi izvor (senzori / API). Jos nije implementiran."""

    _NOT_IMPLEMENTED = "LiveSource nije implementiran - stub za buduce prave senzore/API."

    def known_park_ids(self) -> set[str]:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    def capacity(self, park_id: str) -> float:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    def history_until(self, park_id: str, until: pd.Timestamp) -> pd.Series:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    def grid_bounds(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        raise NotImplementedError(self._NOT_IMPLEMENTED)
