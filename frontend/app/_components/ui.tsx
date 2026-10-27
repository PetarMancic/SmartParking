// Male prezentacione komponente (bez state-a i bez poziva ka backendu).

import { CircleAlert, CircleCheck, CircleHelp, CircleX, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { occupancyStatus, STATUS_META, type OccupancyStatus } from "./status";

const STATUS_ICON: Record<OccupancyStatus, LucideIcon> = {
  free: CircleCheck,
  busy: CircleAlert,
  full: CircleX,
  unknown: CircleHelp,
};

export const controlClass =
  "h-9 rounded-control border border-border bg-surface px-3 text-sm text-ink shadow-xs outline-none transition " +
  "placeholder:text-ink-subtle hover:border-ink-subtle/50 focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-primary/25";

const buttonBase =
  "inline-flex h-9 shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-control px-3.5 text-sm font-medium transition " +
  "outline-none focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-50";

export const buttonClass = {
  primary: `${buttonBase} bg-primary text-white shadow-xs hover:bg-primary-ink focus-visible:ring-primary/35`,
  secondary: `${buttonBase} border border-border bg-surface text-ink shadow-xs hover:bg-surface-2 focus-visible:ring-primary/25`,
  success: `${buttonBase} bg-free-ink text-white shadow-xs hover:bg-[#085a08] focus-visible:ring-free/35`,
  warning: `${buttonBase} bg-busy text-[#3d2800] shadow-xs hover:bg-[#e9a20f] focus-visible:ring-busy/40`,
  danger: `${buttonBase} bg-full text-white shadow-xs hover:bg-full-ink focus-visible:ring-full/35`,
};

export function Card({
  title,
  icon: Icon,
  subtitle,
  action,
  children,
  className = "",
}: {
  title?: ReactNode;
  icon?: LucideIcon;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-card border border-border bg-surface shadow-xs ${className}`}>
      {title && (
        <header className="flex items-start justify-between gap-3 px-4 pt-4">
          <div className="flex min-w-0 items-start gap-2.5">
            {Icon && (
              <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary-ink">
                <Icon className="size-4" aria-hidden />
              </span>
            )}
            <div className="min-w-0">
              <h2 className="text-sm font-semibold leading-7">{title}</h2>
              {subtitle && <div className="-mt-0.5 text-xs text-ink-muted">{subtitle}</div>}
            </div>
          </div>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function CountBadge({ count }: { count: number }) {
  return (
    <span className="mt-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-surface-2 px-1.5 text-xs font-semibold text-ink-muted ring-1 ring-border tabular-nums">
      {count}
    </span>
  );
}

// Status je uvek boja + ikona + tekst (ne samo boja).
export function StatusBadge({ rate, value }: { rate: number | null; value?: string }) {
  const status = occupancyStatus(rate);
  const meta = STATUS_META[status];
  const Icon = STATUS_ICON[status];
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${meta.badgeClass}`}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {value && <span className="font-semibold tabular-nums">{value}</span>}
      {value && <span aria-hidden>·</span>}
      <span>{meta.label}</span>
    </span>
  );
}

export function StatusDot({ status, className = "size-3" }: { status: OccupancyStatus; className?: string }) {
  return (
    <span
      className={`inline-block shrink-0 rounded-full ring-2 ring-white ${className}`}
      style={{ background: STATUS_META[status].color, boxShadow: "0 0 0 1px rgba(15,23,42,0.2)" }}
      aria-hidden
    />
  );
}

export { STATUS_ICON };

export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`block animate-pulse rounded-md bg-border/70 ${className}`} aria-hidden />;
}

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border bg-surface-2 px-4 py-7 text-center">
      <span className="grid size-10 place-items-center rounded-full bg-surface text-ink-subtle ring-1 ring-border">
        <Icon className="size-5" aria-hidden />
      </span>
      <div className="mt-3 text-sm font-semibold">{title}</div>
      {children && <div className="mt-1 max-w-xs text-xs text-ink-muted">{children}</div>}
    </div>
  );
}

export function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-muted">
      {children}
    </label>
  );
}

export function InfoTile({
  icon: Icon,
  iconClass,
  label,
  children,
}: {
  icon: LucideIcon;
  iconClass: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-xl border border-border bg-surface-2 px-3 py-2.5">
      <span className={`grid size-9 shrink-0 place-items-center rounded-lg ${iconClass}`}>
        <Icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-medium uppercase tracking-wide text-ink-subtle">{label}</div>
        <div className="text-sm">{children}</div>
      </div>
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-lg bg-surface-2 px-2.5 py-2 ring-1 ring-border/70">
      <div className="text-[11px] leading-tight text-ink-muted">{label}</div>
      <div className="mt-0.5 text-base font-semibold tabular-nums">{value ?? "-"}</div>
    </div>
  );
}
