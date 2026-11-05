"use client";

import { useEffect, useState } from "react";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { TriangleAlert } from "lucide-react";
import Sparkline, { ActualPoint, ForecastPoint, TypicalPoint } from "./Sparkline";
import { displayOccupancy } from "./occupancy";
import { occupancyStatus, STATUS_META, type OccupancyStatus } from "./_components/status";
import { Skeleton, STATUS_ICON, StatusBadge } from "./_components/ui";

export type Park = {
  park_id: string;
  name: string | null;
  capacity: number;
  lat: number | null;
  lng: number | null;
  type: string | null;
  confirmed: boolean;
};

export type ParkState = {
  park_id: string;
  current_occupancy_rate: number | null;
  current_available_spots: number | null;
  target_time: string | null;
  target_occupancy_rate: number | null;
  target_available_spots: number | null;
  is_prediction: boolean | null;
  horizon_minutes: number | null;
  horizon_clamped: boolean;
  mae: number | null;
};

export type HistoryResponse = {
  park_id: string;
  current_time: string;
  day_of_week: string;
  typical_curve: TypicalPoint[];
  actual_today: ActualPoint[];
};

export type Recommendation = {
  park_id: string;
  lat: number;
  lng: number;
  eta_minutes: number;
  horizon_minutes: number;
  predicted_occupancy_rate: number;
  availability_score: number;
  distance_to_origin_km: number;
  distance_to_destination_km: number;
  score: number;
  // Delovi skora iz backend/recommender.py (score_candidates):
  // skor = w1*predicted_availability + w2*closeness - w3*drive_time
  score_components: {
    predicted_availability: number;
    closeness: number;
    drive_time: number;
    weights: { w1_predicted_availability: number; w2_proximity: number; w3_drive_time: number };
  };
};

export type RouteParking = {
  park_id: string;
  lat: number;
  lng: number;
  distanceToRouteKm: number;
  occupancyRate: number | null;
};

// Status boje po zauzetosti (poglavlje 6) - dataviz skill status paleta:
// good/warning/critical, namerno razlicite od kategorickih boja uloga ispod.
// Pragovi i boje su u _components/status.ts (isti za mapu, legendu i liste).
function occupancyStatusColor(rate: number | null): string {
  return STATUS_META[occupancyStatus(rate)].color;
}

function createDotIcon(color: string, size = 16) {
  return L.divIcon({
    className: "",
    html: `<div class="sp-pin" style="background:${color}"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

// Marker parkinga je "pilula" sa procentom zauzetosti, da se status cita i
// bez boje; preporuceni parking dobija ljubicasti prsten i broj ranga.
function createParkIcon(rate: number | null, highlightRank?: number) {
  const status = occupancyStatus(rate);
  const label = rate === null ? "–" : `${Math.round(rate)}%`;
  const recommended = highlightRank !== undefined;
  const [width, height] = recommended ? [44, 24] : [38, 20];
  const classes = `sp-marker sp-marker--${status}${recommended ? " sp-marker--recommended" : ""}`;
  const rankBadge = recommended ? `<span class="sp-marker__rank">${highlightRank}</span>` : "";
  return L.divIcon({
    className: "",
    html: `<div class="${classes}" style="background:${occupancyStatusColor(rate)}">${label}${rankBadge}</div>`,
    iconSize: [width, height],
    iconAnchor: [width / 2, height / 2],
  });
}

const DESTINATION_ICON = createDotIcon("#e34948", 20);
const START_ICON = createDotIcon("#2a78d6", 20);

const NORWICH_CENTER: [number, number] = [52.6287, 1.2974];

function ClickHandler({ onMapClick }: { onMapClick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) {
      onMapClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function MapBoundsHandler({
  startLocation,
  destination,
  routeGeometry,
}: {
  startLocation: { lat: number; lng: number } | null;
  destination: { lat: number; lng: number } | null;
  routeGeometry: [number, number][];
}) {
  const map = useMap();

  useEffect(() => {
    if (!startLocation || !destination) return;

    const bounds = routeGeometry.length > 1
      ? L.latLngBounds(routeGeometry)
      : L.latLngBounds([
          [startLocation.lat, startLocation.lng],
          [destination.lat, destination.lng],
        ]);

    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
  }, [map, startLocation, destination, routeGeometry]);

  return null;
}

function formatClock(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("sr-RS", { hour: "2-digit", minute: "2-digit" });
}

function ParkPopupBody({
  park,
  state,
  history,
}: {
  park: Park;
  state: ParkState | undefined;
  history: HistoryResponse | undefined;
}) {
  const hasTarget = state?.target_time != null;
  const rate = hasTarget ? state?.target_occupancy_rate ?? null : state?.current_occupancy_rate ?? null;
  const available = hasTarget ? state?.target_available_spots ?? null : state?.current_available_spots ?? null;

  const forecast: ForecastPoint[] =
    state?.is_prediction && state.horizon_minutes !== null
      ? [{ minutesFromNow: state.horizon_minutes, occupancy_rate: state.target_occupancy_rate }]
      : [];

  return (
    <div className="min-w-[260px]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-snug">{park.name || park.park_id}</div>
          {park.type && (
            <span className="mt-1 inline-block rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-ink-muted ring-1 ring-border">
              {park.type}
            </span>
          )}
        </div>
        <StatusBadge rate={rate} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-surface-2 px-2.5 py-2 ring-1 ring-border/70">
          <div className="text-[11px] leading-tight text-ink-muted">
            {hasTarget ? `Zauzetost u ${formatClock(state!.target_time as string)}` : "Trenutna zauzetost"}
          </div>
          <div className="mt-0.5 text-base font-semibold tabular-nums">
            {rate !== null ? `${rate.toFixed(1)}%` : "nema podatka"}
          </div>
          {hasTarget && (
            <div className="text-[11px] font-medium text-ink-subtle">{state?.is_prediction ? "(predikcija)" : "(izmereno)"}</div>
          )}
        </div>
        {available !== null && (
          <div className="rounded-lg bg-surface-2 px-2.5 py-2 ring-1 ring-border/70">
            <div className="text-[11px] leading-tight text-ink-muted">Slobodna mesta</div>
            <div className="mt-0.5 text-base font-semibold tabular-nums">{available}</div>
          </div>
        )}
      </div>

      {state?.horizon_clamped && (
        <div className="mt-2 flex gap-1.5 rounded-lg bg-busy-soft px-2.5 py-1.5 text-xs text-busy-ink">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Napomena: traženo vreme je van dometa modela (~15.5h unapred) - prikazan je maksimalan horizont.
        </div>
      )}
      {state?.mae !== null && state?.mae !== undefined && (
        <div className="mt-2 text-xs text-ink-muted">
          Pouzdanost (tipična greška): <span className="font-semibold text-ink">±{state.mae.toFixed(1)} p.p.</span>
        </div>
      )}

      <div className="mt-3 border-t border-border pt-3">
        {history ? (
          <Sparkline typical={history.typical_curve} actual={history.actual_today} forecast={forecast} now={history.current_time} />
        ) : (
          <Skeleton className="h-[90px] w-[260px]" />
        )}
      </div>
    </div>
  );
}

const LEGEND_STATUSES: OccupancyStatus[] = ["free", "busy", "full", "unknown"];

function LegendStatusRow({ status }: { status: OccupancyStatus }) {
  const meta = STATUS_META[status];
  const Icon = STATUS_ICON[status];
  return (
    <div className="flex items-center gap-2">
      <span
        className="grid h-4 w-7 shrink-0 place-items-center rounded-full ring-2 ring-white"
        style={{ background: meta.color, boxShadow: "0 0 0 1px rgba(15,23,42,0.2)" }}
        aria-hidden
      >
        <Icon className={`size-2.5 ${status === "busy" ? "text-[#3d2800]" : "text-white"}`} strokeWidth={3} />
      </span>
      <span className="whitespace-nowrap font-medium">{meta.label}</span>
      <span className="ml-auto whitespace-nowrap pl-1 text-ink-subtle tabular-nums">{meta.range}</span>
    </div>
  );
}

export default function ParkingMap({
  parks,
  parkStates,
  historyByPark,
  onPopupOpen,
  startLocation,
  destination,
  routeGeometry,
  routeParkings,
  recommendations,
  radiusMeters,
  radiusCenter,
  onMapClick,
}: {
  parks: Park[];
  parkStates: Record<string, ParkState>;
  historyByPark: Record<string, HistoryResponse>;
  onPopupOpen: (parkId: string) => void;
  startLocation: { lat: number; lng: number } | null;
  destination: { lat: number; lng: number } | null;
  routeGeometry: [number, number][];
  routeParkings: RouteParking[];
  recommendations: Recommendation[];
  radiusMeters: number | null;
  radiusCenter: { lat: number; lng: number } | null;
  onMapClick: (lat: number, lng: number) => void;
}) {
  // Legenda je preko mape (gornji desni ugao) i prekrivala bi popup parkinga -
  // dok je popup otvoren, legenda se sklanja.
  const [popupOpen, setPopupOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const recommendedRank = new Map(recommendations.map((r, i) => [r.park_id, i + 1]));
  const routeParkingIds = new Set(routeParkings.map((p) => p.park_id));
  const mappableParks = parks.filter((p) => p.lat !== null && p.lng !== null);

  return (
    <div className="relative h-full w-full">
      <MapContainer center={NORWICH_CENTER} zoom={12} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickHandler onMapClick={onMapClick} />
        <MapBoundsHandler startLocation={startLocation} destination={destination} routeGeometry={routeGeometry} />

        {routeGeometry.length > 1 && (
          <>
            <Polyline pathOptions={{ color: "#ffffff", weight: 9, opacity: 0.9, interactive: false }} positions={routeGeometry} />
            <Polyline pathOptions={{ color: "#2a78d6", weight: 5, opacity: 0.9 }} positions={routeGeometry} />
          </>
        )}

        {radiusCenter && radiusMeters && radiusMeters > 0 && (
          <Circle
            center={[radiusCenter.lat, radiusCenter.lng]}
            radius={radiusMeters}
            pathOptions={{ color: "#4a3aa7", fillColor: "#4a3aa7", fillOpacity: 0.12 }}
          />
        )}

        {mappableParks.map((park) => {
          const state = parkStates[park.park_id];
          const rate = displayOccupancy(state);
          const rank = recommendedRank.get(park.park_id);
          const isRouteParking = routeParkingIds.has(park.park_id);

          return (
            <Marker
              key={park.park_id}
              position={[park.lat as number, park.lng as number]}
              icon={createParkIcon(rate, rank)}
              riseOnHover
              eventHandlers={{
                popupopen: () => {
                  setPopupOpen(true);
                  onPopupOpen(park.park_id);
                },
                popupclose: () => setPopupOpen(false),
              }}
            >
              <Tooltip direction="top" offset={[0, -12]} className="park-label">
                {park.name || park.park_id}
                {isRouteParking ? " (uz rutu)" : ""}
              </Tooltip>
              <Popup>
                <ParkPopupBody park={park} state={state} history={historyByPark[park.park_id]} />
              </Popup>
            </Marker>
          );
        })}

        {startLocation && (
          <Marker position={[startLocation.lat, startLocation.lng]} icon={START_ICON}>
            <Popup>Početna lokacija</Popup>
          </Marker>
        )}

        {destination && (
          <Marker position={[destination.lat, destination.lng]} icon={DESTINATION_ICON}>
            <Popup>Destinacija</Popup>
          </Marker>
        )}
      </MapContainer>

      <div
        className={`absolute right-3 top-3 z-[1000] rounded-card border border-border bg-surface/95 text-[11px] shadow-lg backdrop-blur sm:pointer-events-none sm:w-[196px] sm:p-3 ${popupOpen ? "hidden" : ""}`}
      >
        {/* Na malom ekranu legenda je sklopiva (inace prekriva vecinu mape). */}
        <button
          type="button"
          onClick={() => setLegendOpen((open) => !open)}
          aria-expanded={legendOpen}
          className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-xs font-semibold outline-none focus-visible:ring-3 focus-visible:ring-primary/30 sm:hidden"
        >
          Legenda <span aria-hidden>{legendOpen ? "−" : "+"}</span>
        </button>
        <div className="mb-2 hidden text-xs font-semibold sm:block">Legenda</div>
        <div className={`${legendOpen ? "block" : "hidden"} w-[196px] px-3 pb-3 sm:block sm:w-auto sm:p-0`}>
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-ink-subtle">Zauzetost</div>
          <div className="flex flex-col gap-1.5">
            {LEGEND_STATUSES.map((status) => (
              <LegendStatusRow key={status} status={status} />
            ))}
          </div>
          <div className="mb-1 mt-3 text-[10px] font-medium uppercase tracking-wide text-ink-subtle">Oznake</div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="relative h-4 w-7 shrink-0 rounded-full bg-unknown ring-2 ring-accent" aria-hidden>
                <span className="absolute -right-1.5 -top-1.5 grid size-3 place-items-center rounded-full bg-accent text-[7px] font-bold text-white">
                  1
                </span>
              </span>
              <span className="font-medium">Preporučeno (broj = rang)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="grid w-7 shrink-0 place-items-center" aria-hidden>
                <span className="size-3 rounded-full bg-primary ring-2 ring-white" style={{ boxShadow: "0 0 0 1px rgba(15,23,42,0.25)" }} />
              </span>
              <span className="font-medium">Početna tačka</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="grid w-7 shrink-0 place-items-center" aria-hidden>
                <span className="size-3 rounded-full bg-[#e34948] ring-2 ring-white" style={{ boxShadow: "0 0 0 1px rgba(15,23,42,0.25)" }} />
              </span>
              <span className="font-medium">Destinacija</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="grid w-7 shrink-0 place-items-center" aria-hidden>
                <span className="h-1 w-6 rounded-full bg-primary" />
              </span>
              <span className="font-medium">Ruta</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
