import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { listTraces } from "../api/monitoring";
import {
  formatMs,
  formatNumber,
  Panel,
} from "../components/monitoring/Primitives";
import { ArrowLeft } from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";
import type { MonitoringRange, TraceSummaryInfo } from "../types";

const RANGES: MonitoringRange[] = ["15m", "1h", "6h", "24h", "7d", "30d"];

/** A trace is a failure on the same three cases the metric layer counts. */
function failed(trace: TraceSummaryInfo): boolean {
  return (
    trace.status !== "ok" ||
    trace.status_code === null ||
    trace.status_code >= 500
  );
}

export function AdminTracesPage() {
  const navigate = useNavigate();

  // Set by the "other requests in this conversation" link on a trace, so
  // that link actually narrows the list rather than being decorative.
  const [params, setParams] = useSearchParams();
  const conversation = params.get("conversation");

  const [range, setRange] = useState<MonitoringRange>("24h");
  const [failedOnly, setFailedOnly] = useState(false);
  const [route, setRoute] = useState("");
  const [lookup, setLookup] = useState("");

  const [traces, setTraces] = useState<TraceSummaryInfo[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (before?: string) => {
      setLoading(true);
      setError(null);

      try {
        const response = await listTraces({
          range,
          limit: 50,
          before,
          failed_only: failedOnly || undefined,
          route: route || undefined,
          conversation_id: conversation ?? undefined,
        });

        // Appending on paginate, replacing on a filter change: the cursor
        // is what tells the two apart.
        setTraces((current) =>
          before ? [...current, ...response.traces] : response.traces,
        );
        setCursor(response.next_before);
      } catch (caught) {
        setError(
          caught instanceof Error ? caught.message : "Could not load traces.",
        );
      } finally {
        setLoading(false);
      }
    },
    [range, failedOnly, route, conversation],
  );

  useEffect(() => {
    void load();
  }, [load]);

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
        <div className="admin-inner mon-page" data-stale={loading && traces.length > 0}>
          <div className="mon-header">
            <div>
              <h1>Traces</h1>
              <p className="tagline">
                One request, end to end. Open a trace to see every stage it ran.
              </p>
            </div>

            <div className="mon-ranges" role="group" aria-label="Time range">
              {RANGES.map((option) => (
                <button
                  key={option}
                  type="button"
                  className="mon-range"
                  aria-pressed={range === option}
                  onClick={() => setRange(option)}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>

          <p className="mon-links">
            <Link to="/admin/monitoring">&larr; Monitoring</Link>
          </p>

          {/* Jumping straight to an id is the point of the page: someone
              reports a bad answer and quotes the header they were given. */}
          <form
            className="wf-lookup"
            onSubmit={(event) => {
              event.preventDefault();
              const id = lookup.trim();
              if (id) {
                navigate(`/admin/traces/${encodeURIComponent(id)}`);
              }
            }}
          >
            <input
              type="text"
              value={lookup}
              placeholder="Open a trace id (the X-Trace-ID from a response)"
              onChange={(event) => setLookup(event.target.value)}
              aria-label="Trace id"
            />
            <button type="submit" className="wf-lookup-go">
              Open
            </button>
          </form>

          {conversation && (
            <p className="wf-scope">
              Showing one conversation
              <button
                type="button"
                onClick={() => {
                  params.delete("conversation");
                  setParams(params);
                }}
              >
                clear
              </button>
            </p>
          )}

          <div className="wf-filters">
            <label>
              <input
                type="checkbox"
                checked={failedOnly}
                onChange={(event) => setFailedOnly(event.target.checked)}
              />
              Failures only
            </label>

            <input
              type="text"
              className="wf-route"
              value={route}
              placeholder="Filter by route, e.g. /api/query"
              onChange={(event) => setRoute(event.target.value)}
              aria-label="Route"
            />
          </div>

          {error && <p className="error-text">{error}</p>}

          <Panel title={`${formatNumber(traces.length)} traces`}>
            {traces.length === 0 && !loading ? (
              <p className="mon-empty">No traces match in this window.</p>
            ) : (
              <table className="data-table mon-table wf-list">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Route</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Trace</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.map((trace) => (
                    <tr key={trace.trace_id} data-failed={failed(trace)}>
                      <td>{new Date(trace.started_at).toLocaleTimeString()}</td>
                      <td>{trace.route ?? "unmatched"}</td>
                      <td>
                        {/* Status as a number and a word, never colour
                            alone. */}
                        <span className="wf-status" data-failed={failed(trace)}>
                          {trace.status_code ?? "no response"}
                          {trace.error_type ? ` · ${trace.error_type}` : ""}
                        </span>
                      </td>
                      <td>{formatMs(trace.duration_ms)}</td>
                      <td>
                        <Link
                          to={`/admin/traces/${trace.trace_id}`}
                          className="wf-id"
                        >
                          {trace.trace_id.slice(0, 12)}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {cursor && (
              <button
                type="button"
                className="wf-more"
                disabled={loading}
                onClick={() => void load(cursor)}
              >
                {loading ? "Loading…" : "Load older"}
              </button>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
