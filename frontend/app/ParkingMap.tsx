"use client";

import { useEffect } from "react";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import Sparkline, { ActualPoint, ForecastPoint, TypicalPoint } from "./Sparkline";
import { displayOccupancy } from "./occupancy";

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
function occupancyStatusColor(rate: number | null): string {
  if (rate === null) return "#898781"; // nema ocitavanja (rupa u podacima)
  if (rate < 50) return "#0ca30c"; // good
  if (rate < 80) return "#fab219"; // warning
  return "#d03b3b"; // critical
}

function createDotIcon(color: string, size = 16, ring = "2px solid white") {
  return L.divIcon({
    className: "",
    html: `<div style="background:${color};width:${size}px;height:${size}px;border-radius:50%;border:${ring};box-shadow:0 0 3px rgba(0,0,0,0.6);"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function createParkIcon(rate: number | null, highlightRank?: number) {
  const color = occupancyStatusColor(rate);
  if (highlightRank === undefined) {
    return createDotIcon(color, 14);
  }
  const size = 22;
  return L.divIcon({
    className: "",
    html: `<div style="position:relative;width:${size}px;height:${size}px;">
      <div style="background:${color};width:${size}px;height:${size}px;border-radius:50%;border:3px solid #4a3aa7;box-shadow:0 0 4px rgba(0,0,0,0.6);"></div>
      <div style="position:absolute;top:-6px;right:-6px;background:#4a3aa7;color:white;font-size:10px;font-weight:700;width:16px;height:16px;border-radius:50%;display:flex;align-items:center;justify-content:center;">${highlightRank}</div>
    </div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
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
    <div style={{ minWidth: 260 }}>
      <strong>{park.name || park.park_id}</strong>
      {park.type && <span className="badge bg-secondary-subtle text-secondary-emphasis ms-2">{park.type}</span>}

      {!hasTarget && (
        <div className="small text-muted mt-1">
          Trenutna zauzetost: {rate !== null ? `${rate.toFixed(1)}%` : "nema podatka"}
        </div>
      )}
      {hasTarget && (
        <div className="small text-muted mt-1">
          Zauzetost u {formatClock(state!.target_time as string)}
          {state?.is_prediction ? " (predikcija)" : " (izmereno)"}: {rate !== null ? `${rate.toFixed(1)}%` : "nema podatka"}
        </div>
      )}
      {available !== null && <div className="small text-muted">Slobodna mesta: {available}</div>}
      {state?.horizon_clamped && (
        <div className="small text-warning mt-1">
          Napomena: traženo vreme je van dometa modela (~15.5h unapred) - prikazan je maksimalan horizont.
        </div>
      )}
      {state?.mae !== null && state?.mae !== undefined && (
        <div className="small text-muted">Pouzdanost (tipična greška): ±{state.mae.toFixed(1)} p.p.</div>
      )}

      {history && (
        <div className="mt-2">
          <Sparkline typical={history.typical_curve} actual={history.actual_today} forecast={forecast} now={history.current_time} />
        </div>
      )}
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
  const recommendedRank = new Map(recommendations.map((r, i) => [r.park_id, i + 1]));
  const routeParkingIds = new Set(routeParkings.map((p) => p.park_id));
  const mappableParks = parks.filter((p) => p.lat !== null && p.lng !== null);

  return (
    <div style={{ position: "relative", height: "100%", width: "100%" }}>
      <MapContainer center={NORWICH_CENTER} zoom={12} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickHandler onMapClick={onMapClick} />
        <MapBoundsHandler startLocation={startLocation} destination={destination} routeGeometry={routeGeometry} />

        {routeGeometry.length > 1 && (
          <Polyline pathOptions={{ color: "#2a78d6", weight: 5, opacity: 0.8 }} positions={routeGeometry} />
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
              eventHandlers={{ popupopen: () => onPopupOpen(park.park_id) }}
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
        style={{
          position: "absolute",
          top: 12,
          right: 12,
          zIndex: 1000,
          background: "rgba(255,255,255,0.95)",
          border: "1px solid #dbeafe",
          borderRadius: "0.85rem",
          boxShadow: "0 10px 24px rgba(15, 23, 42, 0.12)",
          padding: "0.7rem 0.8rem",
          pointerEvents: "none",
        }}
      >
        <div className="fw-semibold small mb-2">Legenda</div>
        <div className="d-flex flex-column gap-2 small">
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#0ca30c", display: "inline-block" }} />
            <span>Zauzetost &lt; 50%</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#fab219", display: "inline-block" }} />
            <span>Zauzetost 50-80%</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#d03b3b", display: "inline-block" }} />
            <span>Zauzetost &gt; 80%</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 14, height: 14, borderRadius: "50%", background: "#898781", display: "inline-block", border: "3px solid #4a3aa7" }} />
            <span>Preporučeno (broj = rang)</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#2a78d6", display: "inline-block" }} />
            <span>Početna tačka</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#e34948", display: "inline-block" }} />
            <span>Destinacija</span>
          </div>
        </div>
      </div>
    </div>
  );
}
