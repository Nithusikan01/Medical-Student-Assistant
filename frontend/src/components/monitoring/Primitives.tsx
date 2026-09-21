import type { ReactNode } from "react";

/**
 * The non-chart pieces of the dashboard.
 *
 * Several numbers here are better as a stat tile than as a chart - a single
 * current value with no series behind it is not a bar chart with one bar.
 */

export function formatNumber(value: number): string {
  return value.toLocaleString();
}

export function formatMs(value: number | null): string {
  if (value === null) {
    return "—";
  }

  if (value >= 1000) {
    return `${(value / 1000).toFixed(value >= 10000 ? 0 : 2)} s`;
  }

  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ms`;
}

export function formatPercent(value: number | null, digits = 0): string {
  return value === null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

/**
 * Cost arrives as a decimal string so it survives JSON without becoming a
 * float. Null means no pricing row covered the model, which is a different
 * statement from "$0.00" and is rendered as such.
 */
export function formatCost(value: string | null): string {
  if (value === null) {
    return "not priced";
  }

  const amount = Number(value);

  if (amount === 0) {
    return "$0.00";
  }

  return amount < 0.01 ? `$${amount.toFixed(5)}` : `$${amount.toFixed(2)}`;
}

/**
 * A timestamp as elapsed time, because the question this answers is "is the
 * corpus current" rather than "what time was it".
 *
 * Null is "never", not "now": a knowledge base nothing has ever been
 * ingested into is a real state, and rendering it as a date would be a
 * fiction.
 */
export function formatWhen(iso: string | null): string {
  if (!iso) {
    return "never";
  }

  const then = new Date(iso).getTime();

  if (Number.isNaN(then)) {
    return "unknown";
  }

  const minutes = Math.max(Math.round((Date.now() - then) / 60000), 0);

  if (minutes < 1) {
    return "just now";
  }

  if (minutes < 60) {
    return `${minutes}m ago`;
  }

  const hours = Math.round(minutes / 60);

  if (hours < 48) {
    return `${hours}h ago`;
  }

  return `${Math.round(hours / 24)}d ago`;
}

export function StatTile({
  label,
  value,
  detail,
  tone = "default",
  variant = "number",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "default" | "warning" | "danger";
  /**
   * "text" for values that are words rather than quantities - a route, an
   * environment name. The numeric size overflows a tile as soon as the
   * string is longer than a few characters, and a clipped route is worse
   * than a smaller one.
   */
  variant?: "number" | "text";
}) {
  return (
    <div className="mon-tile" data-tone={tone}>
      <span className="mon-tile-label">{label}</span>
      <span className="mon-tile-value" data-variant={variant}>
        {value}
      </span>
      {detail !== undefined && <span className="mon-tile-detail">{detail}</span>}
    </div>
  );
}

/**
 * A single ratio against a limit. A meter, not a two-slice pie.
 */
export function Meter({
  label,
  value,
  caption,
  tone = "default",
}: {
  label: string;
  value: number;
  caption?: string;
  tone?: "default" | "warning" | "danger";
}) {
  const width = Math.min(Math.max(value, 0), 1) * 100;

  return (
    <div className="mon-meter">
      <div className="mon-meter-label">
        <span>{label}</span>
        <strong>{formatPercent(value)}</strong>
      </div>
      <div className="mon-meter-track">
        <div
          className="mon-meter-fill"
          data-tone={tone}
          style={{ width: `${width}%` }}
        />
      </div>
      {caption && <span className="mon-meter-caption">{caption}</span>}
    </div>
  );
}

export function Panel({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mon-panel">
      <header className="mon-panel-head">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

/**
 * Shown instead of a chart when a window holds nothing.
 *
 * Deliberately not an empty set of axes: "nothing happened" and "everything
 * was zero" are different findings and must not look alike.
 */
export function EmptyState({ message }: { message: string }) {
  return <p className="mon-empty">{message}</p>;
}

/**
 * Consumption against a configured ceiling.
 *
 * Moved here with the Model usage panel when the library page was split:
 * it is a spend view, and spend is the dashboard's question rather than
 * the document library's.
 *
 * A model with no configured limit gets the number and no track. Drawing
 * an empty bar would imply a ceiling that does not exist, and an unlimited
 * model would look perpetually fine rather than unmeasured.
 */
export function UsageMeter({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | null;
}) {
  const level = meterLevel(used, limit);

  const width =
    limit === null || limit <= 0 ? 0 : Math.min(100, (used / limit) * 100);

  return (
    <div className="usage-meter">
      <div className="usage-meter-label">
        <span>{label}</span>
        <span>
          {formatNumber(used)}
          {limit !== null && ` / ${formatNumber(limit)}`}
        </span>
      </div>
      {limit !== null && (
        <div className="usage-meter-track">
          <div
            className="usage-meter-fill"
            data-level={level === "ok" ? undefined : level}
            style={{ width: `${width}%` }}
          />
        </div>
      )}
    </div>
  );
}

function meterLevel(
  used: number,
  limit: number | null,
): "ok" | "warning" | "danger" {
  if (limit === null || limit <= 0) {
    return "ok";
  }

  const ratio = used / limit;

  if (ratio >= 1) {
    return "danger";
  }

  if (ratio >= 0.8) {
    return "warning";
  }

  return "ok";
}
