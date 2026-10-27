// Status zauzetosti - jedini izvor pragova i boja za ceo UI (mapa, legenda,
// popup, preporuke). Pragovi su isti kao ranije u ParkingMap.tsx:
// < 50 % zeleno, 50-80 % zuto, >= 80 % crveno, null = nema ocitavanja.
// Bez importa leaflet-a, pa ga sme uvoziti i page.tsx (SSR).

export type OccupancyStatus = "free" | "busy" | "full" | "unknown";

export function occupancyStatus(rate: number | null): OccupancyStatus {
  if (rate === null) return "unknown";
  if (rate < 50) return "free";
  if (rate < 80) return "busy";
  return "full";
}

export const STATUS_META: Record<
  OccupancyStatus,
  { label: string; range: string; color: string; badgeClass: string }
> = {
  free: { label: "Dosta mesta", range: "< 50 %", color: "#0ca30c", badgeClass: "bg-free-soft text-free-ink ring-free/30" },
  busy: { label: "Popunjava se", range: "50–80 %", color: "#fab219", badgeClass: "bg-busy-soft text-busy-ink ring-busy/40" },
  full: { label: "Skoro puno", range: "≥ 80 %", color: "#d03b3b", badgeClass: "bg-full-soft text-full-ink ring-full/30" },
  unknown: { label: "Nema podatka", range: "–", color: "#898781", badgeClass: "bg-unknown-soft text-ink-muted ring-unknown/30" },
};
