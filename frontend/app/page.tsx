"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import {
  Award,
  CalendarDays,
  ChartLine,
  ChevronDown,
  Clock,
  Eye,
  EyeOff,
  Flag,
  Footprints,
  LoaderCircle,
  MapPin,
  MousePointerClick,
  Pause,
  Play,
  RotateCcw,
  Route,
  SearchX,
  Sparkles,
  SquareParking,
  Timer,
  TriangleAlert,
} from "lucide-react";
import CompareChart, { CompareLegend, type CompareResponse } from "./CompareChart";
import { displayOccupancy } from "./occupancy";
import type { HistoryResponse, Park, ParkState, Recommendation, RouteParking } from "./ParkingMap";
import {
  buttonClass,
  Card,
  controlClass,
  CountBadge,
  EmptyState,
  FieldLabel,
  InfoTile,
  Skeleton,
  Stat,
  StatusBadge,
} from "./_components/ui";

const ParkingMap = dynamic(() => import("./ParkingMap"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full place-items-center bg-surface-2 text-sm text-ink-muted">
      <span className="flex items-center gap-2">
        <LoaderCircle className="size-4 animate-spin" aria-hidden /> Učitavanje mape…
      </span>
    </div>
  ),
});

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
// skor = w1*dostupnost + w2*blizina - w3*vreme_voznje, svaka vrednost u 0-1.
function getScoreParts(recommendation: Recommendation) {
  const { predicted_availability, closeness, drive_time, weights } = recommendation.score_components;
  return [
    { label: "Dostupnost", value: predicted_availability, weight: weights.w1_predicted_availability, sign: "+", barClass: "bg-free" },
    { label: "Blizina cilju", value: closeness, weight: weights.w2_proximity, sign: "+", barClass: "bg-primary" },
    { label: "Vreme vožnje", value: drive_time, weight: weights.w3_drive_time, sign: "−", barClass: "bg-ink-subtle" },
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

  // Esc u dijalogu "Zameniti trenutnu rutu?" radi isto sto i "Otkazi".
  useEffect(() => {
    if (!pendingMapClick) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPendingMapClick(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pendingMapClick]);

  const resetSelection = () => {
    setCurrentLocation(null);
    setDestination(null);
    setRoute(null);
    setRecommendations([]);
    setPendingMapClick(null);
  };

  // Izvedeno samo za prikaz - ne utice na pozive ni na stanje.
  const backendDown =
    error !== null &&
    (error.startsWith("Ne mogu da učitam listu parkinga") ||
      error === "Ne mogu da učitam simulacioni sat." ||
      error === "Ne mogu da učitam stanje parkinga.");
  const mapHint = !currentLocation
    ? "Klikni na mapu da postaviš početnu tačku"
    : !destination
      ? "Klikni na mapu da postaviš destinaciju"
      : null;
  const weights = recommendations[0]?.score_components.weights;

  return (
    <>
      {pendingMapClick && (
        <div className="fixed inset-0 z-[2000] grid place-items-center bg-ink/45 p-4 backdrop-blur-[2px]">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="replace-route-title"
            aria-describedby="replace-route-desc"
            className="w-full max-w-sm rounded-card border border-border bg-surface p-5 shadow-2xl"
          >
            <div className="flex items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-full-soft text-full-ink">
                <TriangleAlert className="size-5" aria-hidden />
              </span>
              <div>
                <h2 id="replace-route-title" className="text-base font-semibold">
                  Zameniti trenutnu rutu?
                </h2>
                <p id="replace-route-desc" className="mt-1 text-sm text-ink-muted">
                  Već imaš izabranu rutu i preporuke. Klik na mapu bi obrisao trenutnu rutu i postavio novu početnu tačku. Da li si siguran?
                </p>
              </div>
            </div>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button type="button" autoFocus onClick={cancelNewRoute} className={buttonClass.secondary}>
                Otkaži
              </button>
              <button type="button" onClick={confirmNewRoute} className={buttonClass.danger}>
                Obriši i započni novu rutu
              </button>
            </div>
          </div>
        </div>
      )}

      <header className="z-[1100] lg:sticky lg:top-0 border-b border-border bg-surface/90 backdrop-blur">
        <div className="flex w-full flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 lg:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-linear-to-br from-primary to-accent text-white shadow-sm">
              <SquareParking className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <h1 className="text-base font-semibold leading-tight">
                Smart Parking <span className="font-normal text-ink-subtle">· Norfolk</span>
              </h1>
              <p className="truncate text-xs text-ink-muted">Ruta i preporuka parkinga na osnovu predikcije zauzetosti</p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3 rounded-xl border border-border bg-surface-2 py-1.5 pl-3 pr-1.5">
            <div className="flex flex-col leading-tight">
              <span className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle" aria-live="polite">
                <span
                  className={`size-2 rounded-full ${simState?.running ? "sp-live-dot bg-free" : simState ? "bg-unknown" : "bg-border"}`}
                  aria-hidden
                />
                {simState ? (simState.running ? "Simulacija radi" : "Pauzirano") : "Povezivanje…"}
              </span>
              <span className="text-sm font-semibold tabular-nums">{formatSimTime(simState?.current_time ?? null)}</span>
            </div>
            {simState?.running ? (
              <button type="button" onClick={handlePause} className={buttonClass.warning}>
                <Pause className="size-4" aria-hidden /> Pauza
              </button>
            ) : (
              <button type="button" onClick={handleStart} className={buttonClass.success}>
                <Play className="size-4" aria-hidden /> Start
              </button>
            )}
            <label htmlFor="sim-speed" className="sr-only">
              Brzina simulacije
            </label>
            <select
              id="sim-speed"
              className={`${controlClass} w-[4.5rem]`}
              value={speed}
              onChange={(e) => handleSpeedChange(Number(e.target.value))}
            >
              {SPEED_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}x</option>
              ))}
            </select>
          </div>
        </div>
      </header>

      <main className="flex w-full flex-1 flex-col gap-4 px-4 py-4 lg:px-6 lg:py-5">
        {/* Kontrole i ruta: na sirokom ekranu jedna pored druge, da mapa dobije visinu.
            Na mobilnom (order) mapa ide odmah ispod headera, pa ruta, pa kontrole. */}
        <div className="order-2 grid gap-4 lg:order-none xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <Card>
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-[minmax(0,1fr)_minmax(0,0.7fr)_minmax(0,1.8fr)]">
              <div>
                <FieldLabel htmlFor="view-time">Vreme (mapa i polazak)</FieldLabel>
                <div className="relative">
                  <Clock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden />
                  <select
                    id="view-time"
                    className={`${controlClass} w-full pl-9`}
                    value={viewTime}
                    onChange={(e) => setViewTime(e.target.value)}
                  >
                    <option value="now">Sada</option>
                    {TIME_OF_DAY_OPTIONS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <p className="mt-1.5 text-xs text-ink-muted">
                  Prošlost/sadašnjost = izmereno; budućnost = predikcija (do ~15.5h unapred).
                </p>
              </div>

              <div>
                <FieldLabel htmlFor="radius">Radius (m, opcionalno)</FieldLabel>
                <div className="relative">
                  <input
                    id="radius"
                    type="number"
                    min={100}
                    max={1000}
                    value={radiusMeters}
                    onChange={(e) => setRadiusMeters(e.target.value)}
                    className={`${controlClass} w-full pr-9`}
                    placeholder="npr. 500"
                  />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-subtle">m</span>
                </div>
                <p className="mt-1.5 text-xs text-ink-muted">Krug hodanja oko destinacije.</p>
              </div>

              <div className="md:col-span-2 2xl:col-span-1">
                <FieldLabel htmlFor="jump-date">Skok na datum (test period)</FieldLabel>
                <div className="flex flex-wrap gap-2">
                  <div className="relative min-w-[140px] flex-1">
                    <CalendarDays className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden />
                    <input
                      id="jump-date"
                      type="date"
                      className={`${controlClass} w-full pl-9`}
                      value={jumpDate}
                      min={simState?.test_start.slice(0, 10)}
                      max={simState ? new Date(new Date(simState.test_end).getTime() - 86400000).toISOString().slice(0, 10) : undefined}
                      onChange={(e) => setJumpDate(e.target.value)}
                    />
                  </div>
                  <select
                    aria-label="Vreme u danu za skok"
                    className={`${controlClass} w-24`}
                    value={jumpTime}
                    onChange={(e) => setJumpTime(e.target.value)}
                  >
                    {TIME_OF_DAY_OPTIONS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                  <button type="button" onClick={handleJump} className={buttonClass.primary}>
                    Postavi vreme
                  </button>
                </div>
                <p className="mt-1.5 text-xs text-ink-muted">Model nije video ove podatke pri treningu.</p>
              </div>
            </div>
          </Card>

          <Card
            className="order-first xl:order-none"
            title="Ruta"
            icon={Route}
            subtitle="Klikni na mapu da odabereš početnu tačku i destinaciju. Prva tačka je start, druga je cilj."
            action={
              <button type="button" onClick={resetSelection} className={buttonClass.secondary}>
                <RotateCcw className="size-4" aria-hidden /> <span className="hidden sm:inline">Resetuj izbor</span>
                <span className="sr-only sm:hidden">Resetuj izbor</span>
              </button>
            }
          >
            <div className="grid gap-2 sm:grid-cols-3">
              <InfoTile icon={MapPin} iconClass="bg-primary-soft text-primary-ink" label="Početna tačka">
                {currentLocation ? (
                  <>
                    <div className="truncate font-semibold">{startPlace?.street || "Učitavanje..."}</div>
                    <div className="truncate text-xs text-ink-muted">{startPlace?.city || "Učitavanje..."}</div>
                  </>
                ) : (
                  <div className="text-ink-muted">Još nije izabrana</div>
                )}
              </InfoTile>
              <InfoTile icon={Flag} iconClass="bg-full-soft text-full-ink" label="Destinacija">
                {destination ? (
                  <>
                    <div className="truncate font-semibold">{destinationPlace?.street || "Učitavanje..."}</div>
                    <div className="truncate text-xs text-ink-muted">{destinationPlace?.city || "Učitavanje..."}</div>
                  </>
                ) : (
                  <div className="text-ink-muted">Klikni na mapu</div>
                )}
              </InfoTile>
              <InfoTile icon={Route} iconClass="bg-accent-soft text-accent" label="Ruta">
                {route ? (
                  <div className="font-semibold tabular-nums">
                    {route.distanceKm.toFixed(1)} km • {Math.round(route.durationMin)} min
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 text-ink-muted">
                    {routeLoading && <LoaderCircle className="size-3.5 animate-spin" aria-hidden />}
                    {routeLoading ? "Učitavanje rute..." : "Čeka se ruta"}
                  </div>
                )}
              </InfoTile>
            </div>
          </Card>
        </div>

        {error && (
          <div role="alert" className="flex gap-3 rounded-card border border-busy/60 bg-busy-soft p-4 text-sm text-busy-ink">
            <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
            <div>
              <div className="font-semibold">{error}</div>
              {backendDown && (
                <div className="mt-1 text-xs">
                  Proveri da li je backend pokrenut (<code className="rounded bg-white/70 px-1 py-0.5 font-mono">npm run backend</code>, port 8000), pa osveži stranicu.
                </div>
              )}
            </div>
          </div>
        )}

        <div className="relative order-1 h-[68vh] min-h-[420px] overflow-hidden lg:order-none rounded-card border border-border bg-surface shadow-xs lg:h-[calc(100vh-7rem)] lg:min-h-[560px]">
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
          {parks.length === 0 && !error && (
            <div className="pointer-events-none absolute left-1/2 top-4 z-[1000] -translate-x-1/2">
              <span className="inline-flex items-center gap-2 rounded-full bg-surface px-3 py-1.5 text-xs font-medium text-ink-muted shadow-md ring-1 ring-border">
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden /> Učitavanje parkinga…
              </span>
            </div>
          )}
          {mapHint && parks.length > 0 && (
            <div className="pointer-events-none absolute inset-x-0 bottom-8 z-[1000] flex justify-center px-4 sm:bottom-auto sm:top-3">
              <span className="inline-flex items-center gap-2 rounded-full bg-ink/85 px-4 py-2 text-sm font-medium text-white shadow-lg backdrop-blur">
                <MousePointerClick className="size-4" aria-hidden /> {mapHint}
              </span>
            </div>
          )}
          {destination && (
            <div className="absolute bottom-8 left-1/2 z-[1000] w-[min(92%,460px)] -translate-x-1/2 sm:bottom-auto sm:top-3 sm:w-[min(56%,460px)]">
              <div className="flex items-center gap-3 rounded-xl border border-border bg-surface/95 p-2.5 pl-3 shadow-lg backdrop-blur">
                {recommendationLoading ? (
                  <span className="flex items-center gap-2 py-1.5 text-sm text-ink-muted">
                    <LoaderCircle className="size-4 animate-spin" aria-hidden /> Računam preporuke…
                  </span>
                ) : recommendations.length === 0 ? (
                  <span className="flex items-center gap-2 py-1.5 text-sm text-ink-muted">
                    <SearchX className="size-4 shrink-0" aria-hidden /> Nema parkinga u trenutnom skupu
                  </span>
                ) : (
                  <>
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-sm font-bold text-white">1</span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-accent">Preporučeno</div>
                      <div className="truncate text-sm font-semibold">
                        {parkName(recommendations[0].park_id)}{" "}
                        <span className="font-normal text-ink-muted">· skor {recommendations[0].score.toFixed(2)}</span>
                      </div>
                    </div>
                    <a href="#preporuke" className={buttonClass.secondary}>
                      <span className="hidden sm:inline">Sve preporuke</span>
                      <span className="sr-only sm:hidden">Sve preporuke</span>
                      <ChevronDown className="size-4" aria-hidden />
                    </a>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Ispod mape: preporuke levo, parkinzi uz rutu i poredjenje desno. */}
        <div className="order-3 grid items-start gap-4 lg:order-none lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <Card
            id="preporuke"
            className="scroll-mt-4 lg:scroll-mt-24"
            title="Top preporuke za cilj"
            icon={Sparkles}
            subtitle="Dostupnost pri dolasku, blizina cilju, vreme vožnje"
            action={<CountBadge count={recommendations.length} />}
          >
            <div aria-live="polite" aria-busy={recommendationLoading}>
              {!destination && !recommendationLoading && (
                <EmptyState icon={MousePointerClick} title="Još nema destinacije">
                  Izaberi cilj na mapi da vidiš najbolje parkinge.
                </EmptyState>
              )}
              {recommendationLoading && (
                <div className="grid gap-3 md:grid-cols-2">
                  {Array.from({ length: 3 }).map((_, index) => (
                    <div key={index} className={`rounded-xl border border-border p-3.5 ${index === 0 ? "md:col-span-2" : ""}`}>
                      <div className="flex items-center gap-3">
                        <Skeleton className="size-8 rounded-full" />
                        <Skeleton className="h-4 w-1/2" />
                        <Skeleton className="ml-auto h-5 w-10" />
                      </div>
                      <Skeleton className="mt-3 h-3 w-4/5" />
                      <Skeleton className="mt-2 h-3 w-3/5" />
                    </div>
                  ))}
                  <span className="sr-only">Učitavanje preporuka…</span>
                </div>
              )}
              {!recommendationLoading && destination && recommendations.length === 0 && (
                <EmptyState icon={SearchX} title="Nema parkinga u trenutnom skupu">
                  Pokušaj da povećaš radius ili promeniš lokaciju.
                </EmptyState>
              )}
              {!recommendationLoading && (!destination || recommendations.length > 0) && recommendations.length > 0 && (
                <ol className="grid gap-3 md:grid-cols-2">
                  {recommendations.map((r, i) => {
                    const reasons = getRecommendationReasons(r, radiusMeters ? Number(radiusMeters) : null);
                    const top = i === 0;

                    return (
                      <li
                        key={r.park_id}
                        className={`rounded-xl p-3.5 ${top ? "border-2 border-accent/45 bg-accent-soft/60 shadow-sm md:col-span-2" : "border border-border bg-surface"}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex min-w-0 items-start gap-3">
                            <span
                              className={`grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold tabular-nums ${top ? "bg-accent text-white" : "bg-surface-2 text-ink-muted ring-1 ring-border"}`}
                              aria-label={`Rang ${i + 1}`}
                            >
                              {i + 1}
                            </span>
                            <div className="min-w-0">
                              {top && (
                                <div className="mb-0.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-accent">
                                  <Award className="size-3.5" aria-hidden /> Preporučeno
                                </div>
                              )}
                              <div className="truncate font-semibold leading-snug">{parkName(r.park_id)}</div>
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="text-[10px] font-medium uppercase tracking-wide text-ink-subtle">Skor</div>
                            <div className={`font-semibold tabular-nums ${top ? "text-xl text-accent" : "text-base"}`}>
                              {r.score.toFixed(2)}
                            </div>
                          </div>
                        </div>

                        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                          <div className="col-span-2 flex flex-wrap items-center justify-between gap-2">
                            <dt className="text-ink-muted">Predikcija za dolazak</dt>
                            <dd>
                              <StatusBadge rate={r.predicted_occupancy_rate} value={`${r.predicted_occupancy_rate}%`} />
                            </dd>
                          </div>
                          <div>
                            <dt className="flex items-center gap-1 text-ink-muted">
                              <Timer className="size-3.5" aria-hidden /> Dolazak
                            </dt>
                            <dd className="mt-0.5 font-medium tabular-nums">
                              ~{Math.round(r.eta_minutes)} min <span className="font-normal text-ink-subtle">· horizont {r.horizon_minutes} min</span>
                            </dd>
                          </div>
                          <div>
                            <dt className="flex items-center gap-1 text-ink-muted">
                              <Footprints className="size-3.5" aria-hidden /> Hodanje do cilja
                            </dt>
                            <dd className="mt-0.5 font-medium tabular-nums">{r.distance_to_destination_km.toFixed(2)} km</dd>
                          </div>
                        </dl>

                        {reasons.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {reasons.map((reason) => (
                              <span
                                key={reason}
                                className="inline-flex items-center rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary-ink"
                              >
                                {reason}
                              </span>
                            ))}
                          </div>
                        )}

                        <div className={`mt-3 rounded-lg p-2.5 ring-1 ring-border/70 ${top ? "bg-surface/80" : "bg-surface-2"}`}>
                          <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
                            Zašto? Delovi skora (vrednost × ponder)
                          </div>
                          <div className="flex flex-col gap-1.5">
                            {getScoreParts(r).map((part) => (
                              <div key={part.label} className="grid grid-cols-[84px_minmax(0,1fr)_auto] items-center gap-2 text-xs">
                                <span className="font-medium">{part.label}</span>
                                <div className="h-1.5 overflow-hidden rounded-full bg-border/80">
                                  <div
                                    className={`h-full rounded-full transition-[width] duration-300 ${part.barClass}`}
                                    style={{ width: `${Math.round(part.value * 100)}%` }}
                                  />
                                </div>
                                <span className="min-w-[88px] text-right text-[11px] tabular-nums text-ink-muted">
                                  {part.sign} {Math.round(part.value * 100)}% × {part.weight}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
              {weights && !recommendationLoading && recommendations.length > 0 && (
                <p className="mt-3 border-t border-border pt-3 font-mono text-[11px] text-ink-muted">
                  skor = {weights.w1_predicted_availability}·dostupnost + {weights.w2_proximity}·blizina − {weights.w3_drive_time}·vreme vožnje
                </p>
              )}
            </div>
          </Card>

          <aside className="flex min-w-0 flex-col gap-4">
            {routeParkings.length > 0 && (
              <Card
                title="Parkinzi uz rutu"
                icon={Route}
                subtitle={`Do ${ROUTE_DISTANCE_LIMIT_KM} km od rute vožnje`}
                action={<CountBadge count={routeParkings.length} />}
              >
                <ul className="divide-y divide-border">
                  {routeParkings.map((p) => (
                    <li key={p.park_id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{parkName(p.park_id)}</div>
                        <div className="text-xs text-ink-muted">{p.distanceToRouteKm} km od rute</div>
                      </div>
                      <StatusBadge
                        rate={p.occupancyRate}
                        value={p.occupancyRate !== null ? `${p.occupancyRate.toFixed(0)}%` : undefined}
                      />
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {compareData && (
              <Card
                title="Predikcija vs stvarnost"
                icon={ChartLine}
                subtitle={
                  <>
                    {compareData.name ?? compareData.park_id} · {formatSimTime(compareData.from_time)}
                  </>
                }
                action={
                  <button
                    type="button"
                    aria-pressed={reveal}
                    className={reveal ? buttonClass.secondary : buttonClass.primary}
                    onClick={() => setReveal((r) => !r)}
                  >
                    {reveal ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                    {reveal ? "Sakrij stvarnost" : "Otkrij stvarnost"}
                  </button>
                }
              >
                <div className="rounded-lg bg-surface-2 p-2 ring-1 ring-border/70">
                  <CompareChart data={compareData} reveal={reveal} showRolling={showRolling} />
                </div>
                <div className="mt-2.5">
                  <CompareLegend showRolling={showRolling} />
                </div>
                <label htmlFor="rolling" className="mt-3 flex w-fit cursor-pointer items-center gap-2 text-xs">
                  <input
                    id="rolling"
                    type="checkbox"
                    className="size-4 cursor-pointer accent-primary"
                    checked={showRolling}
                    onChange={(e) => setShowRolling(e.target.checked)}
                  />
                  Prognoza „sat unapred” kroz ceo dan
                </label>
                {!compareData.has_reading_at_from_time && (
                  <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-busy-soft px-2.5 py-1.5 text-xs text-busy-ink">
                    <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
                    Nema očitavanja u ovom trenutku - prognoza nije moguća.
                  </div>
                )}
                {reveal && (
                  <div className="mt-3">
                    <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
                      Greška za ovaj dan (MAE, p.p.)
                    </div>
                    <div className={`grid gap-2 ${showRolling ? "grid-cols-3" : "grid-cols-2"}`}>
                      <Stat label="Prognoza iz „sada”" value={compareData.mae.forecast} />
                      <Stat label="Tipična kriva" value={compareData.mae.typical_same_slots} />
                      {showRolling && <Stat label="Sat unapred" value={compareData.mae.rolling_1h} />}
                    </div>
                  </div>
                )}
                <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-subtle">
                  <MousePointerClick className="size-3.5" aria-hidden /> Klikni na parking na mapi da ga izabereš.
                </p>
              </Card>
            )}
          </aside>
        </div>
      </main>

      <footer className="w-full px-4 pb-5 text-xs text-ink-subtle lg:px-6">
        Smart Parking · master rad, Elektronski fakultet u Nišu · Podaci: parkinzi Norfolka (Stolfi, Alba, Yao 2020), UK Open Government Licence
      </footer>
    </>
  );
}
