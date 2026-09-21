import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SeriesPointInfo, StageLatencyInfo } from "../../types";
import { EmptyState, formatMs, formatNumber } from "./Primitives";

/**
 * Charts for the monitoring dashboard.
 *
 * Conventions applied throughout, each for a reason:
 *
 *   - one y-axis, never two. Two measures of different scale get two charts.
 *   - hairline solid gridlines, no dashes - a dashed grid reads as a
 *     threshold when it is only a grid.
 *   - a 2px surface gap between stacked segments rather than a stroke
 *     around each mark.
 *   - colours come from CSS custom properties, so the light and dark steps
 *     swap with the theme instead of being flipped programmatically.
 *   - every chart has a table underneath it. Tooltips enhance, never gate.
 */

const AXIS = {
  stroke: "var(--chart-axis)",
  tick: { fill: "var(--chart-ink)", fontSize: 11 },
  tickLine: false,
};

const GRID = {
  stroke: "var(--chart-grid)",
  strokeWidth: 1,
  vertical: false,
};

const TOOLTIP_STYLE = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "10px",
  fontSize: "12px",
  color: "var(--text)",
  boxShadow: "var(--shadow-card)",
};

/** Recharts hands formatters a loose value type; narrow it once, here. */
function asNumber(value: unknown): number {
  return typeof value === "number" ? value : Number(value ?? 0);
}

function shortTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Requests over time, split by outcome.
 *
 * Succeeded is deliberately the quiet colour: it is the bulk of the traffic
 * and not what anyone is scanning for. The two that matter carry hues far
 * enough apart to survive colour-vision deficiency.
 */
export function RequestVolumeChart({ series }: { series: SeriesPointInfo[] }) {
  const hasTraffic = series.some((point) => point.total > 0);

  if (!hasTraffic) {
    return <EmptyState message="No requests in this window." />;
  }

  const data = series.map((point) => ({
    ...point,
    label: shortTime(point.start),
  }));

  return (
    <div className="mon-chart" role="img" aria-label="Requests over time by outcome">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="label" {...AXIS} minTickGap={32} />
          <YAxis {...AXIS} allowDecimals={false} width={44} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "var(--raised)" }}
            formatter={(value: unknown, name: unknown) => [
              formatNumber(asNumber(value)),
              String(name),
            ]}
          />
          {/* stackId groups them; the 2px stroke in the surface colour is the
              gap between segments, not a border around them. */}
          <Bar
            dataKey="succeeded"
            name="Succeeded"
            stackId="outcome"
            fill="var(--chart-ok)"
            stroke="var(--chart-surface)"
            strokeWidth={2}
          />
          <Bar
            dataKey="client_errors"
            name="Client errors"
            stackId="outcome"
            fill="var(--chart-client-error)"
            stroke="var(--chart-surface)"
            strokeWidth={2}
          />
          <Bar
            dataKey="failed"
            name="Failed"
            stackId="outcome"
            fill="var(--chart-failed)"
            stroke="var(--chart-surface)"
            strokeWidth={2}
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>

      {/* Rendered here rather than by Recharts, which colours legend text
          with the series colour. Text wears ink; the swatch beside it
          carries identity. Ordered top-down to match the visual stack. */}
      <Legend
        items={[
          { label: "Failed", color: "var(--chart-failed)" },
          { label: "Client errors", color: "var(--chart-client-error)" },
          { label: "Succeeded", color: "var(--chart-ok)" },
        ]}
      />
    </div>
  );
}

/** A legend whose labels stay in ink. */
function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="mon-legend">
      {items.map((item) => (
        <li key={item.label}>
          <span className="mon-swatch" style={{ background: item.color }} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/**
 * p95 per pipeline stage, slowest first.
 *
 * One series, so one colour for every bar. Shading bars darker-where-bigger
 * would double-encode the length the chart already shows, and these stages
 * have no natural order to carry a ramp anyway.
 */
export function StageLatencyChart({ stages }: { stages: StageLatencyInfo[] }) {
  const data = stages
    .filter((stage) => stage.latency.p95_ms !== null)
    .map((stage) => ({
      stage: stage.stage.replace(/_/g, " "),
      p95: stage.latency.p95_ms as number,
      count: stage.count,
      errors: stage.errors,
    }));

  if (data.length === 0) {
    return <EmptyState message="No stages ran in this window." />;
  }

  return (
    <div className="mon-chart" role="img" aria-label="95th percentile latency by stage">
      <ResponsiveContainer width="100%" height={Math.max(180, data.length * 30 + 28)}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 52, bottom: 0, left: 8 }}
          barCategoryGap={6}
        >
          <CartesianGrid {...GRID} vertical horizontal={false} />
          <XAxis
            type="number"
            {...AXIS}
            tickFormatter={(v: unknown) => formatMs(asNumber(v))}
          />
          <YAxis
            type="category"
            dataKey="stage"
            {...AXIS}
            width={122}
            tickMargin={6}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "var(--raised)" }}
            formatter={(value: unknown) => [formatMs(asNumber(value)), "p95"]}
          />
          <Bar
            dataKey="p95"
            fill="var(--chart-series-1)"
            radius={[0, 4, 4, 0]}
            barSize={14}
            label={{
              position: "right",
              formatter: (value: unknown) => formatMs(asNumber(value)),
              fill: "var(--chart-ink)",
              fontSize: 11,
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Tokens by pipeline stage.
 *
 * Also one series, one colour. The point of this chart is which stage is
 * consuming the budget - three of these stages were not counted at all
 * until token accounting was corrected.
 */
export function TokensByStageChart({
  data,
}: {
  data: { stage: string; total_tokens: number }[];
}) {
  if (data.length === 0) {
    return <EmptyState message="No LLM calls in this window." />;
  }

  const rows = [...data]
    .sort((a, b) => b.total_tokens - a.total_tokens)
    .map((row) => ({ ...row, label: row.stage.replace(/_/g, " ") }));

  return (
    <div className="mon-chart" role="img" aria-label="Tokens by pipeline stage">
      <ResponsiveContainer width="100%" height={Math.max(150, rows.length * 34 + 24)}>
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 64, bottom: 0, left: 8 }}
          barCategoryGap={8}
        >
          <CartesianGrid {...GRID} vertical horizontal={false} />
          <XAxis
            type="number"
            {...AXIS}
            tickFormatter={(v: unknown) => formatNumber(asNumber(v))}
          />
          <YAxis type="category" dataKey="label" {...AXIS} width={122} tickMargin={6} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "var(--raised)" }}
            formatter={(value: unknown) => [formatNumber(asNumber(value)), "tokens"]}
          />
          <Bar
            dataKey="total_tokens"
            fill="var(--chart-series-1)"
            radius={[0, 4, 4, 0]}
            barSize={14}
            label={{
              position: "right",
              formatter: (value: unknown) => formatNumber(asNumber(value)),
              fill: "var(--chart-ink)",
              fontSize: 11,
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Where fused results came from: one retriever, the other, or both.
 *
 * A part-to-whole with three classes, so a single stacked bar rather than a
 * pie - close values are far easier to compare along a shared baseline.
 */
export function RetrievalOriginBar({
  denseOnly,
  overlap,
  bm25Only,
}: {
  denseOnly: number | null;
  overlap: number | null;
  bm25Only: number | null;
}) {
  if (denseOnly === null || overlap === null || bm25Only === null) {
    return <EmptyState message="Nothing was retrieved in this window." />;
  }

  const segments = [
    { key: "Vector only", value: denseOnly, color: "var(--chart-cat-1)" },
    { key: "Both", value: overlap, color: "var(--chart-cat-3)" },
    { key: "Lexical only", value: bm25Only, color: "var(--chart-cat-2)" },
  ];

  return (
    <div className="mon-origin">
      <div className="mon-origin-bar" role="img" aria-label="Retrieval origin shares">
        {segments.map((segment) => (
          <div
            key={segment.key}
            className="mon-origin-segment"
            style={{
              width: `${segment.value * 100}%`,
              background: segment.color,
            }}
            title={`${segment.key}: ${(segment.value * 100).toFixed(0)}%`}
          />
        ))}
      </div>

      {/* Direct labels, not colour alone - and the relief the light-mode
          contrast check asks for. */}
      <ul className="mon-origin-legend">
        {segments.map((segment) => (
          <li key={segment.key}>
            <span className="mon-swatch" style={{ background: segment.color }} />
            {segment.key}
            <strong>{(segment.value * 100).toFixed(0)}%</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

export { Cell };
