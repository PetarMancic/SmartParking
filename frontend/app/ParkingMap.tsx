"use client";

import { useEffect } from "react";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";

export type Park = {
  park_id: string;
  capacity: number;
  lat: number;
  lng: number;
};

export type Recommendation = {
  park_id: string;
  lat: number;
  lng: number;
  predicted_occupancy_rate: number;
  availability_score: number;
  distance_km: number;
  distance_to_origin_km: number;
  distance_to_destination_km: number;
  score: number;
};

export type RouteParking = {
  park_id: string;
  lat: number;
  lng: number;
  distanceToRouteKm: number;
  predicted_occupancy_rate: number;
  availability_score: number;
};

// Obicne obojene tacke umesto slika ikonica - izbegava probleme sa
// ucitavanjem Leaflet default marker slika unutar Next.js bundle-a.
function createDotIcon(color: string, size = 16) {
  return L.divIcon({
    className: "",
    html: `<div style="background:${color};width:${size}px;height:${size}px;border-radius:50%;border:2px solid white;box-shadow:0 0 3px rgba(0,0,0,0.6);"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

const PARK_ICON = createDotIcon("#3b82f6"); // plavo - obican parking
const RECOMMENDED_ICON = createDotIcon("#22c55e", 20); // zeleno - preporuceno
const DESTINATION_ICON = createDotIcon("#ef4444", 20); // crveno - destinacija
const START_ICON = createDotIcon("#0ea5e9", 20); // plavo svetlo - pocetna lokacija
const ROUTE_PARK_ICON = createDotIcon("#22c55e", 20); // zeleno - najbolji parking uz rutu

const BIRMINGHAM_CENTER: [number, number] = [52.4796, -1.8998];

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

export default function ParkingMap({
  parks,
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
  startLocation: { lat: number; lng: number } | null;
  destination: { lat: number; lng: number } | null;
  routeGeometry: [number, number][];
  routeParkings: RouteParking[];
  recommendations: Recommendation[];
  radiusMeters: number | null;
  radiusCenter: { lat: number; lng: number } | null;
  onMapClick: (lat: number, lng: number) => void;
}) {
  const recommendedIds = new Set(recommendations.map((r) => r.park_id));
  const displayedRouteParkings = routeParkings.slice(0, 5);
  const routeParkingIds = new Set(displayedRouteParkings.map((park) => park.park_id));

  return (
    <div style={{ position: "relative", height: "100%", width: "100%" }}>
      <MapContainer
        center={BIRMINGHAM_CENTER}
        zoom={14}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickHandler onMapClick={onMapClick} />
        <MapBoundsHandler startLocation={startLocation} destination={destination} routeGeometry={routeGeometry} />

        {routeGeometry.length > 1 && (
          <Polyline pathOptions={{ color: "#2563eb", weight: 5, opacity: 0.8 }} positions={routeGeometry} />
        )}

        {radiusCenter && radiusMeters && radiusMeters > 0 && (
          <Circle
            center={[radiusCenter.lat, radiusCenter.lng]}
            radius={radiusMeters}
            pathOptions={{ color: "#8b5cf6", fillColor: "#c4b5fd", fillOpacity: 0.2 }}
          />
        )}

        {recommendations.map((park) => (
          <Marker
            key={park.park_id}
            position={[park.lat, park.lng]}
            icon={RECOMMENDED_ICON}
          >
            <Tooltip permanent direction="top" offset={[0, -12]} className="park-label">
              {park.park_id}
            </Tooltip>
            <Popup>
              <strong>{park.park_id}</strong>
              <br />
              Drive (d_A): {park.distance_to_origin_km} km
              <br />
              Walk (d_B): {park.distance_to_destination_km} km
              <br />
              Predviđena popunjenost: {park.predicted_occupancy_rate}%
            </Popup>
          </Marker>
        ))}

        {displayedRouteParkings.map((park) => {
          const icon = ROUTE_PARK_ICON;

          return (
            <Marker
              key={park.park_id}
              position={[park.lat, park.lng]}
              icon={icon}
            >
              <Tooltip permanent direction="top" offset={[0, -12]} className="park-label">
                {park.park_id}
              </Tooltip>
              <Popup>
                <strong>{park.park_id}</strong>
                <br />
                Udaljenost od rute: {park.distanceToRouteKm} km
                <br />
                Predviđena popunjenost: {park.predicted_occupancy_rate}%
                {park.availability_score !== undefined && (
                  <>
                    <br />
                    Dostupnost: {park.availability_score}
                  </>
                )}
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
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#0ea5e9", display: "inline-block" }} />
            <span>Početna tačka</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} />
            <span>Destinacija</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 14, height: 14, borderRadius: "50%", background: "#22c55e", display: "inline-block", border: "2px solid white" }} />
            <span>Preporučeni parking</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#8b5cf6", display: "inline-block" }} />
            <span>Radius</span>
          </div>
        </div>
      </div>
    </div>
  );
}
