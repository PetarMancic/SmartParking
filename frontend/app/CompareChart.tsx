"use client";

// Grafik "predikcija vs stvarnost" za jedan dan (korak 2, PLAN_ZAVRSETKA.md).
// Cist SVG kao i Sparkline.tsx - bez chart biblioteke. Iste boje kao Sparkline:
// plavo = stvarno, narandzasto = prognoza, sivo isprekidano = tipicno.

export type ComparePoint = {
  time: string;
  actual: number | null;
  forecast: number | null;
  rolling_1h: number | null;
  typical: number | null;
};

export type CompareResponse = {
  park_id: string;
  name: string | null;
  date: string;
  day_of_week: string;
  from_time: string;
  has_reading_at_from_time: boolean;
  points: ComparePoint[];
  mae: { forecast: number | null; typical_same_slots: number | null; rolling_1h: number | null };
};

const WIDTH = 360;
const HEIGHT = 170;
const LEFT = 30;
const RIGHT = 8;
const TOP = 8;
const BOTTOM = 20;
const START_MINUTES = 7 * 60; // merenja su ~08:00-23:00
const END_MINUTES = 24 * 60;

const COLORS = {
  actual: "#2a78d6",
  forecast: "#eb6834",
  rolling: "#7c5cc4",
  typical: "#898781",
  grid: "#e4e3dc",
  axis: "#52514e",
};

function minutesOfDay(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

function x(minutes: number): number {
  const t = (minutes - START_MINUTES) / (END_MINUTES - START_MINUTES);
  return LEFT + Math.max(0, Math.min(1, t)) * (WIDTH - LEFT - RIGHT);
}

function y(rate: number): number {
  const clamped = Math.max(0, Math.min(100, rate));
  return HEIGHT - BOTTOM - (clamped / 100) * (HEIGHT - TOP - BOTTOM);
}

// Polyline segmenti - prekida liniju na rupama u podacima (null), umesto da
// spaja tacke preko rupe.
function segments(points: ComparePoint[], key: keyof Omit<ComparePoint, "time">): string[] {
  const result: string[] = [];
  let current: string[] = [];
  for (const p of points) {
    const value = p[key];
    if (value === null || minutesOfDay(p.time) < START_MINUTES) {
      if (current.length > 1) result.push(current.join(" "));
      current = [];
      continue;
    }
    current.push(`${x(minutesOfDay(p.time))},${y(value)}`);
  }
  if (current.length > 1) result.push(current.join(" "));
  return result;
}

export default function CompareChart({
  data,
  reveal,
  showRolling,
}: {
  data: CompareResponse;
  reveal: boolean;
  showRolling: boolean;
}) {
  const nowMinutes = minutesOfDay(data.from_time);
  // Bez "otkrivanja" ne prikazujemo nista sto je posle simuliranog "sada" -
  // ni stvarne vrednosti, ni "sat unapred" predikcije koje bi koristile
  // podatke iz buducnosti.
  const visible = reveal ? data.points : data.points.filter((p) => minutesOfDay(p.time) <= nowMinutes);

  const lines = [
    { key: "typical" as const, points: data.points, color: COLORS.typical, width: 1.5, dash: "3,2" },
    ...(showRolling ? [{ key: "rolling_1h" as const, points: visible, color: COLORS.rolling, width: 1.5, dash: "" }] : []),
    { key: "actual" as const, points: visible, color: COLORS.actual, width: 2, dash: "" },
    { key: "forecast" as const, points: data.points, color: COLORS.forecast, width: 2, dash: "5,3" },
  ];

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" role="img" aria-label="Predikcija naspram stvarne zauzetosti">
      {[0, 50, 100].map((v) => (
        <g key={v}>
          <line x1={LEFT} x2={WIDTH - RIGHT} y1={y(v)} y2={y(v)} stroke={COLORS.grid} strokeWidth={1} />
          <text x={LEFT - 4} y={y(v) + 3} fontSize={9} textAnchor="end" fill={COLORS.axis}>{v}%</text>
        </g>
      ))}
      {[8, 12, 16, 20, 24].map((h) => (
        <text key={h} x={x(h * 60)} y={HEIGHT - 6} fontSize={9} textAnchor="middle" fill={COLORS.axis}>
          {String(h % 24).padStart(2, "0")}h
        </text>
      ))}

      {lines.map((line) =>
        segments(line.points, line.key).map((pts, i) => (
          <polyline
            key={`${line.key}-${i}`}
            points={pts}
            fill="none"
            stroke={line.color}
            strokeWidth={line.width}
            strokeDasharray={line.dash || undefined}
          />
        ))
      )}

      <line x1={x(nowMinutes)} x2={x(nowMinutes)} y1={TOP} y2={HEIGHT - BOTTOM} stroke={COLORS.axis} strokeWidth={1} strokeDasharray="2,2" />
      <text x={x(nowMinutes) + 3} y={TOP + 8} fontSize={9} fill={COLORS.axis}>sada</text>
    </svg>
  );
}

export function CompareLegend({ showRolling }: { showRolling: boolean }) {
  const items = [
    { label: "stvarno", color: COLORS.actual },
    { label: "prognoza iz „sada”", color: COLORS.forecast },
    ...(showRolling ? [{ label: "prognoza sat ranije", color: COLORS.rolling }] : []),
    { label: "tipično (prosek dana)", color: COLORS.typical },
  ];
  return (
    <div className="d-flex flex-wrap gap-2" style={{ fontSize: 11 }}>
      {items.map((item) => (
        <span key={item.label} style={{ color: item.color }}>▬ {item.label}</span>
      ))}
    </div>
  );
}
