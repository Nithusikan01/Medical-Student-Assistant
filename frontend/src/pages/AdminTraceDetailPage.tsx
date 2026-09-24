import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getTrace } from "../api/monitoring";
import {
  formatCost,
  formatMs,
  formatNumber,
  Panel,
  StatTile,
} from "../components/monitoring/Primitives";
import { Waterfall } from "../components/monitoring/Waterfall";
import { ArrowLeft } from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";
import type { TraceDetailResponse } from "../types";

/**
 * One request, end to end.
 *
 * The page the whole observability upgrade exists for: given the id from a
 * response header, show what actually happened - which stages ran, how
 * long each took, what each one found, and what the request cost.
 */
export function AdminTraceDetailPage() {
  const { traceId = "" } = useParams();

  const [detail, setDetail] = useState<TraceDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    getTrace(traceId)
      .then((response) => {
        if (!cancelled) {
          setDetail(response);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof Error ? caught.message : "Could not load the trace.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [traceId]);

  const failed =
    detail !== null &&
    (detail.trace.status !== "ok" ||
      detail.trace.status_code === null ||
      detail.trace.status_code >= 500);

  return (
    <div className="admin-shell">
      <div className="admin-bar">
        <Link to="/" className="back-link">
          <ArrowLeft />
          Back to chat
        </Link>
        <ThemeToggle compact />
      </div>

      <div className="admin-body">
        <div className="admin-inner mon-page">
          <div>
            <h1>Trace</h1>
            <p className="tagline wf-trace-id">{traceId}</p>
          </div>

          <p className="mon-links">
            <Link to="/admin/traces">&larr; All traces</Link>
          </p>

          {loading && <p className="mon-empty">Loading&hellip;</p>}

          {error && (
            <p className="error-text">
              {error}
              {/* Telemetry is written by a background thread on an
                  interval, so a trace asked for the instant its response
                  returned may genuinely not be stored yet. */}
              {" "}
              A trace is written a moment after its request finishes; if this
              one is very recent, try again.
            </p>
          )}

          {detail && (
            <>
              <div className="mon-tiles">
                <StatTile
                  label="Route"
                  variant="text"
                  value={detail.trace.route ?? "unmatched"}
                  detail={detail.trace.request_id ?? undefined}
                />
                <StatTile
                  label="Status"
                  variant={detail.trace.status_code === null ? "text" : "number"}
                  value={detail.trace.status_code ?? "no response"}
                  detail={detail.trace.error_type ?? undefined}
                  tone={failed ? "danger" : "default"}
                />
                <StatTile
                  label="Duration"
                  value={formatMs(detail.trace.duration_ms)}
                  detail={new Date(detail.trace.started_at).toLocaleString()}
                />
                <StatTile
                  label="Tokens"
                  value={formatNumber(detail.total_tokens)}
                  detail={`${detail.tokens.length} LLM call${
                    detail.tokens.length === 1 ? "" : "s"
                  }`}
                />
                <StatTile
                  label="Estimated cost"
                  value={formatCost(detail.estimated_cost_usd)}
                />
                <StatTile
                  label="Environment"
                  variant="text"
                  value={detail.trace.environment ?? "—"}
                  detail={detail.trace.app_version ?? undefined}
                />
              </div>

              <Panel
                title="Timeline"
                description="Select a stage to see what it recorded. Nested stages are indented under the one that opened them."
              >
                <Waterfall
                  spans={detail.spans}
                  traceStart={detail.trace.started_at}
                  traceDuration={detail.trace.duration_ms}
                />
              </Panel>

              {detail.tokens.length > 0 && (
                <Panel
                  title="LLM calls"
                  description="Every call the request made, not only the one that produced the answer."
                >
                  <table className="data-table mon-table cards-on-phone llm-calls">
                    <thead>
                      <tr>
                        <th>Stage</th>
                        <th>Model</th>
                        <th>Prompt</th>
                        <th>Completion</th>
                        <th>Total</th>
                        <th>Estimated cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.tokens.map((call, index) => (
                        <tr key={`${call.stage}-${index}`}>
                          <td className="call-stage">
                            {call.stage.replace(/_/g, " ")}
                          </td>
                          <td className="call-model">{call.model_id}</td>
                          <td data-label="Prompt">
                            {formatNumber(call.prompt_tokens)}
                          </td>
                          <td data-label="Completion">
                            {formatNumber(call.completion_tokens)}
                          </td>
                          <td data-label="Total">
                            {formatNumber(call.total_tokens)}
                          </td>
                          <td data-label="Cost">
                            {formatCost(call.estimated_cost_usd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Panel>
              )}

              {detail.trace.conversation_id && (
                <p className="mon-links">
                  <Link
                    to={`/admin/traces?conversation=${detail.trace.conversation_id}`}
                  >
                    Other requests in this conversation &rarr;
                  </Link>
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
