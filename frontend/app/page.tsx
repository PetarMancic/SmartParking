"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import CompareChart, { CompareLegend, type CompareResponse } from "./CompareChart";
import { displayOccupancy } from "./occupancy";
import type { HistoryResponse, Park, ParkState, Recommendation, RouteParking } from "./ParkingMap";

const ParkingMap = dynamic(() => import("./ParkingMap"), { ssr: false });

const API_URL = "http://127.0.0.1:8000";
const POLL_INTERVAL_MS = 3000;
const ROUTE_DISTANCE_LIMIT_KM = 2.0;
const ROUTE_RESULT_LIMIT = 5;
const SPEED_OPTIONS = [1, 2, 10, 60, 500];

// Vreme u danu, na 30-min mrezi - isto kao mreza merenja senzora (poglavlje 3).
// "now" je posebna vrednost = trenutno simulirano vreme (bez biranja).
const TIME_OF_DAY_OPTIONS = Array.from({ length: 48 }, (_, i) => {
  const h = String(Math.floor(i / 2)).padStart(2, "0");
  const m = i % 2 === 0 ? "00" : "30";
  return `${h}:${m}`;
});

type SimulationState = {
  current_time: string;
  running: boolean;
  speed_minutes_per_second: number;
  tick_minutes: number;
  grid_start: string;
  grid_end: string;
  test_start: string;
  test_end: string; // ekskluzivno
};

type LatLng = { lat: number; lng: number };
type RouteData = { geometry: [number, number][]; distanceKm: number; durationMin: number };
type PlaceLabel = { displayName: string; city: string; street: string };

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number) {
  const earthRadiusKm = 6371;
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const deltaPhi = ((lat2 - lat1) * Math.PI) / 180;
  const deltaLambda = ((lng2 - lng1) * Math.PI) / 180;

  const a =
    Math.sin(deltaPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2;

  return 2 * earthRadiusKm * Math.asin(Math.sqrt(a));
}

function distanceToSegmentKm(lat: number, lng: number, start: LatLng, end: LatLng) {
  const dx = end.lng - start.lng;
  const dy = end.lat - start.lat;

  if (dx === 0 && dy === 0) {
    return haversineKm(lat, lng, start.lat, start.lng);
  }

  const dot = (lat - start.lat) * dx + (lng - start.lng) * dy;
  const segmentLengthSquared = dx * dx + dy * dy;
  const t = Math.max(0, Math.min(1, dot / segmentLengthSquared));

  const projectedLat = start.lat + t * dy;
  const projectedLng = start.lng + t * dx;
  return haversineKm(lat, lng, projectedLat, projectedLng);
}

function distanceToRouteKm(lat: number, lng: number, geometry: [number, number][]) {
  if (geometry.length < 2) return Number.POSITIVE_INFINITY;

  let minDistance = Number.POSITIVE_INFINITY;
  for (let i = 0; i < geometry.length - 1; i += 1) {
    const [lat1, lng1] = geometry[i];
    const [lat2, lng2] = geometry[i + 1];
    const segmentDistance = distanceToSegmentKm(lat, lng, { lat: lat1, lng: lng1 }, { lat: lat2, lng: lng2 });
    minDistance = Math.min(minDistance, segmentDistance);
  }

  return minDistance;
}

function formatSimTime(iso: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("sr-Latn-RS", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function getRecommendationReasons(recommendation: Recommendation, radiusMeters: number | null) {
  const reasons: string[] = [];

  if (recommendation.availability_score >= 0.6) {
    reasons.push("Velika dostupnost");
  }

  const walkRadiusLimitKm = radiusMeters ? radiusMeters / 1000 : null;
  if (walkRadiusLimitKm && recommendation.distance_to_destination_km <= walkRadiusLimitKm) {
    reasons.push("U okviru radijusa hodanja");
  } else if (recommendation.distance_to_destination_km <= 0.3) {
    reasons.push("U okviru radijusa hodanja");
  }

  return reasons;
}

// Delovi skora tacno kako ih racuna backend (recommender.score_candidates):
// skor = w1*dostupnost + w2*blizina - w3*saobracaj, svaka vrednost u 0-1.
function getScoreParts(recommendation: Recommendation) {
  const { predicted_availability, closeness, traffic, weights } = recommendation.score_components;
  return [
    { label: "Dostupnost", value: predicted_availability, weight: weights.w1_predicted_availability, sign: "+", barClass: "bg-success" },
    { label: "Blizina cilju", value: closeness, weight: weights.w2_proximity, sign: "+", barClass: "bg-info" },
    { label: "Saobraćaj", value: traffic, weight: weights.w3_traffic, sign: "−", barClass: "bg-secondary" },
  ];
}

async function fetchPlaceLabel(location: LatLng): Promise<PlaceLabel> {
  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${location.lat}&lon=${location.lng}`
    );
    const data = await response.json();

    const displayName = data?.display_name || "Nepoznata lokacija";
    const address = data?.address || {};
    const street = [address.road, address.neighbourhood, address.suburb].filter(Boolean).join(", ");
    const city = [address.city, address.town, address.village, address.county].filter(Boolean).join(", ");

    return {
      displayName,
      city: city || "Nepoznat grad",
      street: street || "Nepoznata ulica",
    };
  } catch {
    return {
      displayName: "Nepoznata lokacija",
      city: "Nepoznat grad",
      street: "Nepoznata ulica",
    };
  }
}

export default function Home() {
  const [parks, setParks] = useState<Park[]>([]);
  const [parkStates, setParkStates] = useState<Record<string, ParkState>>({});
  const [historyByPark, setHistoryByPark] = useState<Record<string, HistoryResponse>>({});
  const [simState, setSimState] = useState<SimulationState | null>(null);
  const [speed, setSpeed] = useState(2);
  const [viewTime, setViewTime] = useState<string>("now"); // "now" ili "HH:MM"

  const [currentLocation, setCurrentLocation] = useState<LatLng | null>(null);
  const [destination, setDestination] = useState<LatLng | null>(null);
  const [pendingMapClick, setPendingMapClick] = useState<LatLng | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recommendationLoading, setRecommendationLoading] = useState(false);
  const [radiusMeters, setRadiusMeters] = useState<string>("");
  const [route, setRoute] = useState<RouteData | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startPlace, setStartPlace] = useState<PlaceLabel | null>(null);
  const [destinationPlace, setDestinationPlace] = useState<PlaceLabel | null>(null);

  // Demo: skok na datum iz test perioda + poredjenje predikcije i stvarnosti.
  const [jumpDate, setJumpDate] = useState("2017-11-18");
  const [jumpTime, setJumpTime] = useState("10:00");
  const [compareParkId, setCompareParkId] = useState<string | null>(null);
  const [compareData, setCompareData] = useState<CompareResponse | null>(null);
  const [reveal, setReveal] = useState(false);
  const [showRolling, setShowRolling] = useState(false);

  // Parkovi + simulirano stanje - ucitaj jednom i onda pollaj (poglavlje 7).
  useEffect(() => {
    fetch(`${API_URL}/parks`)
      .then((res) => res.json())
      .then(setParks)
      .catch(() => setError("Ne mogu da učitam listu parkinga. Da li backend radi na :8000?"));
  }, []);

  // Datum simuliranog "sada" (samo datumski deo) - izabrano vreme u danu se
  // vezuje za taj isti datum, da bi target_time bio apsolutan ISO trenutak.
  const simDateStr = simState?.current_time ? simState.current_time.slice(0, 10) : null;

  const targetTimeIso = useMemo(() => {
    if (viewTime === "now" || !simDateStr) return null;
    return `${simDateStr}T${viewTime}:00`;
  }, [viewTime, simDateStr]);

  useEffect(() => {
    let cancelled = false;

    const poll = () => {
      fetch(`${API_URL}/simulation/state`)
        .then((res) => res.json())
        .then((data) => !cancelled && setSimState(data))
        .catch(() => !cancelled && setError("Ne mogu da učitam simulacioni sat."));

      const stateParams = new URLSearchParams();
      if (targetTimeIso) stateParams.set("target_time", targetTimeIso);

      fetch(`${API_URL}/state?${stateParams}`)
        .then((res) => res.json())
        .then((data) => {
          if (cancelled) return;
          const byId: Record<string, ParkState> = {};
          for (const p of data.parks ?? []) byId[p.park_id] = p;
          setParkStates(byId);
        })
        .catch(() => !cancelled && setError("Ne mogu da učitam stanje parkinga."));
    };

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [targetTimeIso]);

  const handleStart = () => {
    setError(null);
    fetch(`${API_URL}/simulation/start?speed=${speed}`, { method: "POST" })
      .then((res) => res.json())
      .then(setSimState)
      .catch(() => setError("Ne mogu da pokrenem simulaciju."));
  };

  const handlePause = () => {
    fetch(`${API_URL}/simulation/pause`, { method: "POST" })
      .then((res) => res.json())
      .then(setSimState)
      .catch(() => setError("Ne mogu da pauziram simulaciju."));
  };

  const handleSpeedChange = (value: number) => {
    setSpeed(value);
    fetch(`${API_URL}/simulation/speed?factor=${value}`, { method: "POST" })
      .then((res) => res.json())
      .then(setSimState)
      .catch(() => undefined);
  };

  const handleJump = () => {
    setError(null);
    setReveal(false);
    fetch(`${API_URL}/simulation/reset?start_time=${jumpDate}T${jumpTime}:00`, { method: "POST" })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json()).detail);
        return res.json();
      })
      .then(setSimState)
      .catch((e) => setError(`Ne mogu da postavim vreme: ${e.message}`));
  };

  // Ime parkinga za prikaz u listama (sifra ako ime nije poznato).
  const parkNames = useMemo(() => new Map(parks.map((p) => [p.park_id, p.name ?? p.park_id])), [parks]);
  const parkName = (parkId: string) => parkNames.get(parkId) ?? parkId;

  // Parking za poredjenje: izabran klikom na marker, inace prvi sa koordinatama.
  const effectiveCompareParkId = compareParkId ?? parks.find((p) => p.lat !== null)?.park_id ?? null;
  const simTimeStr = simState?.current_time ? simState.current_time.slice(11, 16) : null;

  useEffect(() => {
    if (!effectiveCompareParkId || !simDateStr || !simTimeStr) return;
    let cancelled = false;
    const params = new URLSearchParams({ park_id: effectiveCompareParkId, date: simDateStr, from_time: simTimeStr });
    fetch(`${API_URL}/compare?${params}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => !cancelled && setCompareData(data))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [effectiveCompareParkId, simDateStr, simTimeStr]);

  const handlePopupOpen = (parkId: string) => {
    setCompareParkId(parkId);
    fetch(`${API_URL}/history?park_id=${encodeURIComponent(parkId)}`)
      .then((res) => res.json())
      .then((data: HistoryResponse) => setHistoryByPark((prev) => ({ ...prev, [parkId]: data })))
      .catch(() => undefined);
  };

  useEffect(() => {
    if (!currentLocation) {
      setStartPlace(null);
      return;
    }

    fetchPlaceLabel(currentLocation).then(setStartPlace);
  }, [currentLocation]);

  useEffect(() => {
    if (!destination) {
      setDestinationPlace(null);
      return;
    }

    fetchPlaceLabel(destination).then(setDestinationPlace);
  }, [destination]);

  useEffect(() => {
    if (!currentLocation || !destination) {
      setRecommendations([]);
      return;
    }

    setRecommendationLoading(true);
    setError(null);

    const params = new URLSearchParams({
      origin_lat: String(currentLocation.lat),
      origin_lng: String(currentLocation.lng),
      dest_lat: String(destination.lat),
      dest_lng: String(destination.lng),
    });

    if (radiusMeters) {
      params.set("radius", radiusMeters);
    }
    if (targetTimeIso) {
      // Vozac ne krece nuzno odmah - ako je izabrano vreme u buducnosti,
      // koristi se kao vreme polaska (dolazak se racuna od tog trenutka).
      params.set("departure_time", targetTimeIso);
    }

    fetch(`${API_URL}/recommend?${params}`)
      .then((res) => res.json())
      .then(setRecommendations)
      .catch(() => setError("Ne mogu da učitam preporuke."))
      .finally(() => setRecommendationLoading(false));
  }, [currentLocation, destination, radiusMeters, targetTimeIso]);

  useEffect(() => {
    if (!currentLocation || !destination) {
      setRoute(null);
      return;
    }

    const fetchRoute = async () => {
      setRouteLoading(true);
      setError(null);

      try {
        const routeUrl = `https://router.project-osrm.org/route/v1/driving/${currentLocation.lng},${currentLocation.lat};${destination.lng},${destination.lat}?overview=full&geometries=geojson`;
        const response = await fetch(routeUrl);
        const routeJson = await response.json();
        const geometry = routeJson?.routes?.[0]?.geometry?.coordinates?.map(([lng, lat]: [number, number]) => [lat, lng] as [number, number]) ?? [];

        if (!geometry.length) {
          setRoute(null);
          setError("Ruta nije pronađena za ove dve lokacije.");
          return;
        }

        const distanceKm = routeJson.routes[0].distance / 1000;
        const durationMin = routeJson.routes[0].duration / 60;
        setRoute({ geometry, distanceKm, durationMin });
      } catch {
        setError("Ne mogu da učitam rutu.");
      } finally {
        setRouteLoading(false);
      }
    };

    fetchRoute();
  }, [currentLocation, destination]);

  // Parkinzi uz rutu - izvedeno iz vec ucitanog /state (bez dodatnih poziva po parkingu).
  const routeParkings: RouteParking[] = useMemo(() => {
    if (!route || route.geometry.length < 2) return [];

    const candidates = parks
      .filter((p) => p.lat !== null && p.lng !== null)
      .map((park) => {
        const dist = distanceToRouteKm(park.lat as number, park.lng as number, route.geometry);
        if (dist > ROUTE_DISTANCE_LIMIT_KM) return null;

        const state = parkStates[park.park_id];
        const occupancyRate = displayOccupancy(state);

        return {
          park_id: park.park_id,
          lat: park.lat as number,
          lng: park.lng as number,
          distanceToRouteKm: Number(dist.toFixed(2)),
          occupancyRate,
        } satisfies RouteParking;
      })
      .filter((c): c is RouteParking => c !== null)
      .sort((a, b) => a.distanceToRouteKm - b.distanceToRouteKm)
      .slice(0, ROUTE_RESULT_LIMIT);

    return candidates;
  }, [route, parks, parkStates]);

  const handleMapClick = (lat: number, lng: number) => {
    if (!currentLocation) {
      setCurrentLocation({ lat, lng });
      setError(null);
      return;
    }

    if (!destination) {
      setDestination({ lat, lng });
      return;
    }

    // Ruta je vec izabrana - ne brisi je odmah (lak je slucajan klik u vozilu),
    // nego trazi potvrdu pre nego sto se zameni.
    setPendingMapClick({ lat, lng });
  };

  const confirmNewRoute = () => {
    if (!pendingMapClick) return;
    setCurrentLocation(pendingMapClick);
    setDestination(null);
    setRoute(null);
    setPendingMapClick(null);
  };

  const cancelNewRoute = () => setPendingMapClick(null);

  const resetSelection = () => {
    setCurrentLocation(null);
    setDestination(null);
    setRoute(null);
    setRecommendations([]);
    setPendingMapClick(null);
  };

  return (
    <main className="py-3 px-2 px-lg-3">
      {pendingMapClick && (
        <div
          className="d-flex align-items-center justify-content-center"
          style={{ position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.45)", zIndex: 2000 }}
        >
          <div className="card border-0 shadow-lg rounded-4" style={{ maxWidth: 360 }}>
            <div className="card-body p-4">
              <h2 className="h6 mb-2">Zameniti trenutnu rutu?</h2>
              <p className="small text-muted mb-3">
                Već imaš izabranu rutu i preporuke. Klik na mapu bi obrisao trenutnu rutu i postavio novu početnu tačku. Da li si siguran?
              </p>
              <div className="d-flex gap-2 justify-content-end">
                <button type="button" onClick={cancelNewRoute} className="btn btn-outline-secondary btn-sm">
                  Otkaži
                </button>
                <button type="button" onClick={confirmNewRoute} className="btn btn-danger btn-sm">
                  Obriši i započni novu rutu
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      <div className="container-fluid">
        <div className="card border-0 shadow-lg rounded-4 overflow-hidden">
          <div className="card-body p-3 p-lg-3">
            <div className="row g-3">
              <div className="col-12 col-lg-8 d-flex flex-column">
                <div className="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-2 mb-2">
                  <div>
                    <div className="d-inline-flex align-items-center gap-2 px-2 py-1 rounded-pill bg-primary-subtle text-primary-emphasis mb-2">
                      <span className="rounded-circle bg-gradient" style={{ width: 8, height: 8, background: "linear-gradient(135deg, #3b82f6, #8b5cf6)" }} />
                      <span className="small fw-semibold">Smart Parking · Norfolk</span>
                    </div>
                    <h1 className="h5 mb-1">Ruta i preporuka parkinga</h1>
                    <p className="text-muted small mb-0">
                      Klikni na mapu da odabereš početnu tačku i destinaciju. Prva tačka je start, druga je cilj.
                    </p>
                  </div>
                  <button type="button" onClick={resetSelection} className="btn btn-outline-primary">
                    Resetuj izbor
                  </button>
                </div>

                <div className="card border-0 mb-2" style={{ background: "linear-gradient(135deg, #eef6ff 0%, #fdf2f8 100%)" }}>
                  <div className="card-body">
                    <div className="row g-3 align-items-end">
                      <div className="col-12 col-md-5">
                        <label className="form-label fw-semibold">Simulacija</label>
                        <div className="d-flex align-items-center gap-2 flex-wrap">
                          <span className="fw-semibold">{formatSimTime(simState?.current_time ?? null)}</span>
                          {simState?.running ? (
                            <button type="button" onClick={handlePause} className="btn btn-sm btn-warning">Pauza</button>
                          ) : (
                            <button type="button" onClick={handleStart} className="btn btn-sm btn-success">Start</button>
                          )}
                          <select
                            className="form-select form-select-sm"
                            style={{ width: 110 }}
                            value={speed}
                            onChange={(e) => handleSpeedChange(Number(e.target.value))}
                          >
                            {SPEED_OPTIONS.map((s) => (
                              <option key={s} value={s}>{s}x</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div className="col-12 col-md-4">
                        <label className="form-label fw-semibold">Vreme (mapa i polazak)</label>
                        <select
                          className="form-select form-select-sm"
                          value={viewTime}
                          onChange={(e) => setViewTime(e.target.value)}
                        >
                          <option value="now">Sada</option>
                          {TIME_OF_DAY_OPTIONS.map((t) => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        </select>
                        <div className="form-text">
                          Prošlost/sadašnjost = izmereno; budućnost = predikcija (do ~15.5h unapred).
                        </div>
                      </div>
                      <div className="col-12 col-md-3">
                        <label className="form-label fw-semibold">Radius (m, opcionalno)</label>
                        <input
                          type="number"
                          min={100}
                          max={1000}
                          value={radiusMeters}
                          onChange={(e) => setRadiusMeters(e.target.value)}
                          className="form-control"
                          placeholder="npr. 500"
                        />
                      </div>
                    </div>
                    <div className="d-flex align-items-end gap-2 flex-wrap mt-2">
                      <div>
                        <label className="form-label small fw-semibold mb-1">Skok na datum (test period)</label>
                        <input
                          type="date"
                          className="form-control form-control-sm"
                          value={jumpDate}
                          min={simState?.test_start.slice(0, 10)}
                          max={simState ? new Date(new Date(simState.test_end).getTime() - 86400000).toISOString().slice(0, 10) : undefined}
                          onChange={(e) => setJumpDate(e.target.value)}
                        />
                      </div>
                      <select className="form-select form-select-sm" style={{ width: 90 }} value={jumpTime} onChange={(e) => setJumpTime(e.target.value)}>
                        {TIME_OF_DAY_OPTIONS.map((t) => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                      <button type="button" onClick={handleJump} className="btn btn-sm btn-primary">Postavi vreme</button>
                      <span className="form-text m-0">Model nije video ove podatke pri treningu.</span>
                    </div>
                  </div>
                </div>

                <div className="row g-2 mb-2">
                  <div className="col-12 col-md-4">
                    <div className="card border-0 shadow-sm h-100">
                      <div className="card-body">
                        <div className="text-uppercase small text-muted">Početna tačka</div>
                        {currentLocation ? (
                          <div className="mt-2">
                            <div className="fw-semibold">{startPlace?.street || "Učitavanje..."}</div>
                            <div className="small text-muted">{startPlace?.city || "Učitavanje..."}</div>
                          </div>
                        ) : (
                          <div className="text-muted mt-2">Još nije izabrana</div>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="col-12 col-md-4">
                    <div className="card border-0 shadow-sm h-100">
                      <div className="card-body">
                        <div className="text-uppercase small text-muted">Destinacija</div>
                        {destination ? (
                          <div className="mt-2">
                            <div className="fw-semibold">{destinationPlace?.street || "Učitavanje..."}</div>
                            <div className="small text-muted">{destinationPlace?.city || "Učitavanje..."}</div>
                          </div>
                        ) : (
                          <div className="text-muted mt-2">Klikni na mapu</div>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="col-12 col-md-4">
                    <div className="card border-0 shadow-sm h-100">
                      <div className="card-body">
                        <div className="text-uppercase small text-muted">Ruta</div>
                        {route ? (
                          <div className="fw-semibold mt-2">{route.distanceKm.toFixed(1)} km • {Math.round(route.durationMin)} min</div>
                        ) : (
                          <div className="text-muted mt-2">{routeLoading ? "Učitavanje rute..." : "Čeka se ruta"}</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="rounded-4 overflow-hidden border border-secondary-subtle shadow-sm" style={{ height: "75vh", minHeight: 640 }}>
                  <ParkingMap
                    parks={parks}
                    parkStates={parkStates}
                    historyByPark={historyByPark}
                    onPopupOpen={handlePopupOpen}
                    startLocation={currentLocation}
                    destination={destination}
                    routeGeometry={route?.geometry ?? []}
                    routeParkings={routeParkings}
                    recommendations={recommendations}
                    radiusMeters={radiusMeters ? Number(radiusMeters) : null}
                    radiusCenter={destination}
                    onMapClick={handleMapClick}
                  />
                </div>
              </div>

              <div className="col-12 col-lg-4">
                <div className="d-flex flex-column gap-2 h-100">
                  {error && (
                    <div className="alert alert-warning mb-0" role="alert">
                      {error}
                    </div>
                  )}

                  {compareData && (
                    <div className="card border-0 shadow-sm">
                      <div className="card-body">
                        <div className="d-flex justify-content-between align-items-start mb-1 gap-2">
                          <div>
                            <h2 className="h6 mb-0">Predikcija vs stvarnost</h2>
                            <div className="small text-muted">
                              {compareData.name ?? compareData.park_id} · {formatSimTime(compareData.from_time)}
                            </div>
                          </div>
                          <button
                            type="button"
                            className={`btn btn-sm ${reveal ? "btn-outline-secondary" : "btn-outline-primary"}`}
                            onClick={() => setReveal((r) => !r)}
                          >
                            {reveal ? "Sakrij stvarnost" : "Otkrij stvarnost"}
                          </button>
                        </div>
                        <CompareChart data={compareData} reveal={reveal} showRolling={showRolling} />
                        <CompareLegend showRolling={showRolling} />
                        <div className="form-check form-check-inline small mt-1">
                          <input id="rolling" type="checkbox" className="form-check-input" checked={showRolling} onChange={(e) => setShowRolling(e.target.checked)} />
                          <label htmlFor="rolling" className="form-check-label">Prognoza „sat unapred” kroz ceo dan</label>
                        </div>
                        {!compareData.has_reading_at_from_time && (
                          <div className="small text-warning-emphasis">Nema očitavanja u ovom trenutku - prognoza nije moguća.</div>
                        )}
                        {reveal && (
                          <div className="small mt-1">
                            Greška za ovaj dan (MAE, p.p.): prognoza iz „sada” <b>{compareData.mae.forecast ?? "-"}</b> · tipična kriva{" "}
                            <b>{compareData.mae.typical_same_slots ?? "-"}</b>
                            {showRolling && <> · sat unapred <b>{compareData.mae.rolling_1h ?? "-"}</b></>}
                          </div>
                        )}
                        <div className="small text-muted mt-1">Klikni na parking na mapi da ga izabereš.</div>
                      </div>
                    </div>
                  )}

                  {routeParkings.length > 0 && (
                    <div className="card border-0 shadow-sm">
                      <div className="card-body">
                        <div className="d-flex justify-content-between align-items-center mb-2">
                          <h2 className="h6 mb-0">Parkinzi uz rutu</h2>
                          <span className="badge bg-info-subtle text-info-emphasis">{routeParkings.length}</span>
                        </div>
                        {routeParkings.map((p) => (
                          <div key={p.park_id} className="small d-flex justify-content-between border-bottom py-1">
                            <span>{parkName(p.park_id)} ({p.distanceToRouteKm} km od rute)</span>
                            <span className="fw-semibold">{p.occupancyRate !== null ? `${p.occupancyRate.toFixed(0)}%` : "-"}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="card border-0 shadow-sm flex-grow-1" style={{ minHeight: 320 }}>
                    <div className="card-body d-flex flex-column p-3 h-100">
                      <div className="d-flex justify-content-between align-items-center mb-2">
                        <h2 className="h6 mb-0">Top preporuke za cilj</h2>
                        <span className="badge bg-success-subtle text-success-emphasis">{recommendations.length}</span>
                      </div>

                      {!destination && !recommendationLoading && (
                        <p className="text-muted small mb-0">Izaberi cilj na mapi da vidiš najbolje parkinge.</p>
                      )}
                      {recommendationLoading && (
                        <div className="d-flex flex-column gap-2 mt-2">
                          {Array.from({ length: 3 }).map((_, index) => (
                            <div key={index} className="border rounded-3 p-2 bg-light">
                              <div className="placeholder-glow">
                                <span className="placeholder col-7 mb-2" />
                                <span className="placeholder col-5" />
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      {!recommendationLoading && destination && recommendations.length === 0 && (
                        <div className="border rounded-3 p-3 mt-2 bg-light text-center">
                          <div className="fw-semibold">Nema parkinga u trenutnom skupu</div>
                          <div className="small text-muted mt-1">Pokušaj da povećaš radius ili promeniš lokaciju.</div>
                        </div>
                      )}
                      {!recommendationLoading && (!destination || recommendations.length > 0) && (
                        <div className="overflow-auto mt-2 flex-grow-1">
                          {recommendations.map((r, i) => {
                            const reasons = getRecommendationReasons(r, radiusMeters ? Number(radiusMeters) : null);

                            return (
                              <div key={r.park_id} className="border rounded-3 p-2 mt-2 bg-white shadow-sm">
                                <div className="d-flex justify-content-between align-items-start gap-2">
                                  <div className="fw-semibold small">{i + 1}. {parkName(r.park_id)}</div>
                                  <span className="badge bg-success-subtle text-success-emphasis">{r.score.toFixed(2)}</span>
                                </div>
                                <div className="small text-muted mt-1">
                                  Predikcija za dolazak (~{Math.round(r.eta_minutes)} min, horizont {r.horizon_minutes} min): {r.predicted_occupancy_rate}%
                                </div>
                                <div className="small text-muted">Hodanje do cilja: {r.distance_to_destination_km.toFixed(2)} km</div>

                                {reasons.length > 0 && (
                                  <div className="d-flex flex-wrap gap-1 mt-2">
                                    {reasons.map((reason) => (
                                      <span key={reason} className="badge bg-primary-subtle text-primary-emphasis">
                                        {reason}
                                      </span>
                                    ))}
                                  </div>
                                )}

                                <div className="mt-2">
                                  <div className="small text-muted mb-1">Delovi skora (vrednost × ponder)</div>
                                  <div className="d-flex flex-column gap-1">
                                    {getScoreParts(r).map((part) => (
                                      <div key={part.label} className="d-flex align-items-center gap-2">
                                        <span className="small fw-semibold" style={{ minWidth: 90 }}>{part.label}</span>
                                        <div className="progress flex-grow-1" style={{ height: "6px" }}>
                                          <div className={`progress-bar ${part.barClass}`} style={{ width: `${Math.round(part.value * 100)}%` }} />
                                        </div>
                                        <span className="small text-muted" style={{ minWidth: 92, textAlign: "right" }}>
                                          {part.sign} {Math.round(part.value * 100)}% × {part.weight}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
