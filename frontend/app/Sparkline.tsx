"use client";

export type TypicalPoint = { time: string; avg_occupancy_rate: number | null };
export type ActualPoint = { time: string; occupancy_rate: number | null };
export type ForecastPoint = { minutesFromNow: number; occupancy_rate: number | null };

const WIDTH = 260;
const HEIGHT = 90;
const PADDING = 6;
const MINUTES_IN_DAY = 24 * 60;

function xForMinutes(minutes: number): number {
  const clamped = Math.max(0, Math.min(MINUTES_IN_DAY, minutes));
  return PADDING + (clamped / MINUTES_IN_DAY) * (WIDTH - 2 * PADDING);
}

function yForRate(rate: number): number {
  const clamped = Math.max(0, Math.min(100, rate));
  return HEIGHT - PADDING - (clamped / 100) * (HEIGHT - 2 * PADDING);
}

function minutesOfDay(isoTime: string): number {
  const d = new Date(isoTime);
  return d.getHours() * 60 + d.getMinutes();
}

export default function Sparkline({
  typical,
  actual,
  forecast,
  now,
}: {
  typical: TypicalPoint[];
  actual: ActualPoint[];
  forecast: ForecastPoint[];
  now: string;
}) {
  const nowMinutes = minutesOfDay(now);

  const typicalPoints = typical
    .map((p, i) => (p.avg_occupancy_rate === null ? null : `${xForMinutes(i * 30)},${yForRate(p.avg_occupancy_rate)}`))
    .filter((p): p is string => p !== null)
    .join(" ");

  const actualKnown = actual.filter((p) => p.occupancy_rate !== null);
  const actualPoints = actualKnown
    .map((p) => `${xForMinutes(minutesOfDay(p.time))},${yForRate(p.occupancy_rate as number)}`)
    .join(" ");

  const lastActual = actualKnown[actualKnown.length - 1];
  const forecastKnown = forecast.filter((p) => p.occupancy_rate !== null);
  const forecastPoints = lastActual
    ? [
        `${xForMinutes(nowMinutes)},${yForRate(lastActual.occupancy_rate as number)}`,
        ...forecastKnown.map((p) => `${xForMinutes(nowMinutes + p.minutesFromNow)},${yForRate(p.occupancy_rate as number)}`),
      ].join(" ")
    : "";

  return (
    <div>
      <svg width={WIDTH} height={HEIGHT} role="img" aria-label="Istorija i prognoza zauzetosti">
        <rect x={0} y={0} width={WIDTH} height={HEIGHT} fill="#fcfcfb" />
        {typicalPoints && (
          <polyline points={typicalPoints} fill="none" stroke="#898781" strokeWidth={1.5} strokeDasharray="3,2" />
        )}
        {actualPoints && <polyline points={actualPoints} fill="none" stroke="#2a78d6" strokeWidth={2} />}
        {forecastPoints && (
          <polyline points={forecastPoints} fill="none" stroke="#eb6834" strokeWidth={2} strokeDasharray="1,3" />
        )}
        {forecastKnown.map((p, i) => (
          <circle
            key={i}
            cx={xForMinutes(nowMinutes + p.minutesFromNow)}
            cy={yForRate(p.occupancy_rate as number)}
            r={3}
            fill="#eb6834"
          />
        ))}
        <line
          x1={xForMinutes(nowMinutes)}
          y1={PADDING}
          x2={xForMinutes(nowMinutes)}
          y2={HEIGHT - PADDING}
          stroke="#c3c2b7"
          strokeWidth={1}
        />
      </svg>
      <div className="d-flex gap-2 small" style={{ fontSize: 10, color: "#52514e" }}>
        <span style={{ color: "#898781" }}>▬▬ tipično (dow prosek)</span>
        <span style={{ color: "#2a78d6" }}>▬▬ stvarno</span>
        <span style={{ color: "#eb6834" }}>▬▬ prognoza</span>
      </div>
    </div>
  );
}
