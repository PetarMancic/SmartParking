import type { ParkState } from "./ParkingMap";

// Odvojeno od ParkingMap.tsx: page.tsx ovo uvozi direktno, a ParkingMap.tsx
// uvozi leaflet koji pristupa `window` i ne sme da se ucita na serveru (SSR).

// Prikazana zauzetost: ciljno vreme ako je izabrano (stvarno ili predvidjeno -
// vidi state.is_prediction), inace trenutno.
export function displayOccupancy(state: ParkState | undefined): number | null {
  if (!state) return null;
  if (state.target_time !== null) return state.target_occupancy_rate;
  return state.current_occupancy_rate;
}
