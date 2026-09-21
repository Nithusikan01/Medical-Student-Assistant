import { useState } from "react";

import type { SpanInfo } from "../../types";
import { formatMs, formatNumber } from "./Primitives";

/**
 * One request's spans as a timeline.
 *
 * Hand-drawn rather than a charting component: this is a Gantt, and CSS
 * does proportional bars with nesting better than a plot library would.
 *
 * Two facts about the data shape the rendering.
 *
 * Offsets come from `started_at`, widths from `duration_ms`, and those are
 * measured by different clocks - the wall clock for one, perf_counter for
 * the other. The wall clock is the coarser of the two, which is why spans
 * carry an explicit `sequence`: a parent and the child it opens routinely
 * share a timestamp. That is harmless here (spans starting in the same
 * tick did start together) but it does mean a child's bar can compute
 * slightly past its parent's end, so bars are clamped to the trace.
 *
 * Ordering is always by `sequence`. Never by `started_at`.
 */

function stageLabel(stage: string): string {
  return stage.replace(/_/g, " ");
}

/** Metadata keys already shown as columns; not repeated in the drawer. */
const SHOWN_ELSEWHERE = new Set(["stage", "status", "duration_ms"]);

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }

  if (typeof value === "number") {
    return Number.isInteger(value) ? formatNumber(value) : value.toFixed(4);
  }

  if (Array.isArray(value)) {
    return value.join(", ");
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

export function Waterfall({
  spans,
  traceStart,
  traceDuration,
}: {
  spans: SpanInfo[];
  traceStart: string;
  traceDuration: number;
}) {
  const [open, setOpen] = useState<string | null>(null);

  if (spans.length === 0) {
    return (
      <p className="mon-empty">
        No spans recorded. Routes other than the query path do not run the
        pipeline.
      </p>
    );
  }

  const base = new Date(traceStart).getTime();

  // The trace's own duration is the scale, so every bar in every trace is
  // read against the same axis: the whole request.
  const scale = Math.max(traceDuration, 1);

  return (
    <div className="wf">
      <div className="wf-axis">
        <span>0 ms</span>
        <span>{formatMs(scale / 2)}</span>
        <span>{formatMs(scale)}</span>
      </div>

      {spans.map((span) => {
        const offset = Math.max(new Date(span.started_at).getTime() - base, 0);

        const left = Math.min((offset / scale) * 100, 100);
        const width = Math.max(
          Math.min((span.duration_ms / scale) * 100, 100 - left),
          0.4,
        );

        const nested = span.parent_span_id !== null;
        const isOpen = open === span.span_id;
        const keys = Object.keys(span.metadata).filter(
          (key) => !SHOWN_ELSEWHERE.has(key),
        );

        return (
          <div className="wf-row" key={span.span_id}>
            <button
              type="button"
              className="wf-bar-row"
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? null : span.span_id)}
            >
              <span className="wf-label" data-nested={nested}>
                {stageLabel(span.stage)}
              </span>

              <span className="wf-track">
                <span
                  className="wf-bar"
                  data-status={span.status}
                  style={{ left: `${left}%`, width: `${width}%` }}
                />
              </span>

              <span className="wf-duration">{formatMs(span.duration_ms)}</span>
            </button>

            {isOpen && (
              <div className="wf-detail">
                {span.status !== "ok" && (
                  <p className="wf-error">
                    failed with <strong>{span.error_type ?? "an error"}</strong>
                  </p>
                )}

                {keys.length === 0 ? (
                  <p className="mon-empty">This stage recorded no metadata.</p>
                ) : (
                  <dl className="wf-meta">
                    {keys.map((key) => (
                      <div key={key}>
                        <dt>{key.replace(/_/g, " ")}</dt>
                        <dd>{formatValue(span.metadata[key])}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
