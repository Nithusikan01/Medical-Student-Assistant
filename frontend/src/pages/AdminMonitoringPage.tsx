import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  getErrors,
  getOverview,
  getPerformance,
  getRetrieval,
  getTokens,
} from "../api/monitoring";
import {
  RequestVolumeChart,
  RetrievalOriginBar,
  StageLatencyChart,
  TokensByStageChart,
} from "../components/monitoring/Charts";
import {
  EmptyState,
  formatCost,
  formatMs,
  formatNumber,
  formatPercent,
  Meter,
  Panel,
  StatTile,
} from "../components/monitoring/Primitives";
import { ArrowLeft } from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";
import type {
  ErrorsResponse,
  MonitoringRange,
  OverviewResponse,
  PerformanceResponse,
  RetrievalResponse,
  TokensResponse,
} from "../types";

const RANGES: { value: MonitoringRange; label: string }[] = [
  { value: "15m", label: "15m" },
  { value: "1h", label: "1h" },
  { value: "6h", label: "6h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
];

interface Data {
  overview: OverviewResponse;
  performance: PerformanceResponse;
  tokens: TokensResponse;
  retrieval: RetrievalResponse;
  errors: ErrorsResponse;
}

export function AdminMonitoringPage() {
  const [range, setRange] = useState<MonitoringRange>("24h");
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (selected: MonitoringRange) => {
    setLoading(true);
    setError(null);

    try {
      const params = { range: selected };

      const [overview, performance, tokens, retrieval, errors] = await Promise.all([
        getOverview(params),
        getPerformance(params),
        getTokens(params),
        getRetrieval(params),
        getErrors(params),
      ]);

      setData({ overview, performance, tokens, retrieval, errors });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load monitoring data.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(range);
  }, [load, range]);

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
        {/* One filter row above everything it scopes, never per-chart. */}
        <div className="admin-inner mon-page" data-stale={loading && data !== null}>
          <div className="mon-header">
            <div>
              <h1>Monitoring</h1>
              <p className="tagline">
                What the RAG pipeline did, measured from real requests.
              </p>
            </div>

            <div className="mon-ranges" role="group" aria-label="Time range">
              {RANGES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="mon-range"
                  aria-pressed={range === option.value}
                  onClick={() => setRange(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <p className="mon-links">
            <Link to="/admin/documents">Library, users and quotas &rarr;</Link>
          </p>

          {error && <p className="error-text">{error}</p>}

          {loading && data === null && <p className="mon-empty">Loading&hellip;</p>}

          {data && <Dashboard data={data} />}
        </div>
      </div>
    </div>
  );
}

function Dashboard({ data }: { data: Data }) {
  const { overview, performance, tokens, retrieval, errors } = data;
  const { requests } = overview;

  return (
    <>
      <div className="mon-tiles">
        <StatTile
          label="Requests"
          value={formatNumber(requests.total)}
          detail={`${requests.requests_per_minute.toFixed(2)}/min`}
        />
        <StatTile
          label="Success rate"
          value={formatPercent(requests.success_rate)}
          detail={`${formatNumber(requests.client_errors)} client errors`}
          tone={requests.failure_rate > 0.05 ? "danger" : "default"}
        />
        <StatTile
          label="Failed"
          value={formatNumber(requests.failed)}
          detail={formatPercent(requests.failure_rate, 1)}
          tone={requests.failed > 0 ? "danger" : "default"}
        />
        <StatTile
          label="p95 latency"
          value={formatMs(requests.latency.p95_ms)}
          detail={`p50 ${formatMs(requests.latency.p50_ms)}`}
        />
        <StatTile label="Tokens" value={formatNumber(overview.total_tokens)} />
        <StatTile
          label="Estimated cost"
          value={formatCost(overview.estimated_cost_usd)}
          detail={
            overview.pricing_configured ? undefined : "no pricing configured"
          }
        />
        <StatTile
          label="In flight"
          value={formatNumber(overview.in_flight.current)}
          detail={`peak ${overview.in_flight.peak} · this process`}
        />
      </div>

      <Panel
        title="Requests over time"
        description="Succeeded is the quiet colour; client errors and failures are what to scan for."
      >
        <RequestVolumeChart series={performance.series} />

        {/* The chart's table twin: every value it plots, reachable without
            hovering. */}
        <details className="mon-table-toggle">
          <summary>Table view</summary>
          <table className="data-table mon-table">
            <thead>
              <tr>
                <th>Bucket</th>
                <th>Succeeded</th>
                <th>Client errors</th>
                <th>Failed</th>
                <th>p95</th>
              </tr>
            </thead>
            <tbody>
              {performance.series
                .filter((point) => point.total > 0)
                .map((point) => (
                  <tr key={point.start}>
                    <td>{new Date(point.start).toLocaleString()}</td>
                    <td>{formatNumber(point.succeeded)}</td>
                    <td>{formatNumber(point.client_errors)}</td>
                    <td>{formatNumber(point.failed)}</td>
                    <td>{formatMs(point.p95_ms)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </details>

        {performance.routes.length > 0 && (
          <details className="mon-table-toggle">
            <summary>By route</summary>
            <table className="data-table mon-table">
              <thead>
                <tr>
                  <th>Route</th>
                  <th>Requests</th>
                </tr>
              </thead>
              <tbody>
                {performance.routes.map((route) => (
                  <tr key={route.route}>
                    <td>{route.route}</td>
                    <td>{formatNumber(route.count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </Panel>

      <Panel
        title="Where the time goes"
        description="95th percentile per pipeline stage, slowest first. Nested stages include their children."
      >
        <StageLatencyChart stages={performance.stages} />

        <details className="mon-table-toggle">
          <summary>Table view</summary>
          <table className="data-table mon-table">
            <thead>
              <tr>
                <th>Stage</th>
                <th>Calls</th>
                <th>p50</th>
                <th>p95</th>
                <th>p99</th>
                <th>Errors</th>
              </tr>
            </thead>
            <tbody>
              {performance.stages.map((stage) => (
                <tr key={stage.stage}>
                  <td>{stage.stage.replace(/_/g, " ")}</td>
                  <td>{formatNumber(stage.count)}</td>
                  <td>{formatMs(stage.latency.p50_ms)}</td>
                  <td>{formatMs(stage.latency.p95_ms)}</td>
                  <td>{formatMs(stage.latency.p99_ms)}</td>
                  <td>{stage.errors > 0 ? formatNumber(stage.errors) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </Panel>

      <Panel
        title="Tokens and cost"
        description="Every LLM call a request makes, not just the answer."
      >
        <TokensByStageChart data={tokens.by_stage} />

        <table className="data-table mon-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Calls</th>
              <th>Prompt</th>
              <th>Completion</th>
              <th>Total</th>
              <th>Estimated cost</th>
            </tr>
          </thead>
          <tbody>
            {tokens.by_model.length === 0 && (
              <tr>
                <td colSpan={6}>No LLM calls in this window.</td>
              </tr>
            )}
            {tokens.by_model.map((row) => (
              <tr key={row.model_id}>
                <td>{row.model_id}</td>
                <td>{formatNumber(row.calls)}</td>
                <td>{formatNumber(row.prompt_tokens)}</td>
                <td>{formatNumber(row.completion_tokens)}</td>
                <td>{formatNumber(row.total_tokens)}</td>
                <td>{formatCost(row.estimated_cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel
        title="Retrieval"
        description={retrieval.offline_metrics_note}
      >
        {retrieval.retrievers.length === 0 ? (
          <EmptyState message="No retrieval ran in this window." />
        ) : (
          <div className="mon-grid">
            <div className="mon-meters">
              {retrieval.retrievers.map((retriever) => (
                <Meter
                  key={retriever.stage}
                  label={`${retriever.stage.replace(/_/g, " ")} returned nothing`}
                  value={retriever.empty_rate}
                  caption={`${formatNumber(retriever.calls)} calls · top score ${
                    retriever.top_score.mean === null
                      ? "—"
                      : retriever.top_score.mean.toFixed(3)
                  }`}
                  tone={retriever.empty_rate > 0.5 ? "danger" : "default"}
                />
              ))}

              {retrieval.fusion && (
                <Meter
                  label="Degraded to a single retriever"
                  value={retrieval.fusion.single_retriever_rate}
                  caption="Hybrid retrieval running on one half, with nothing failing"
                  tone={
                    retrieval.fusion.single_retriever_rate > 0.5 ? "danger" : "default"
                  }
                />
              )}
            </div>

            {retrieval.fusion && (
              <div>
                <h3 className="mon-subhead">Where results came from</h3>
                <RetrievalOriginBar
                  denseOnly={retrieval.fusion.dense_only_share}
                  overlap={retrieval.fusion.overlap_share}
                  bm25Only={retrieval.fusion.bm25_only_share}
                />
              </div>
            )}
          </div>
        )}

        {retrieval.reranking && (
          <div className="mon-rerank">
            <h3 className="mon-subhead">Reranking</h3>

            <div className="mon-tiles">
              <StatTile
                label="Changed the selection"
                value={formatPercent(retrieval.reranking.change_rate)}
                detail="not a claim that it improved it"
              />
              <StatTile
                label="Degraded"
                value={formatPercent(retrieval.reranking.degraded_rate)}
                detail={Object.entries(retrieval.reranking.reranker_usage)
                  .map(([name, count]) => `${name} ${count}`)
                  .join(" · ")}
                tone={retrieval.reranking.degraded_rate > 0 ? "warning" : "default"}
              />
              <StatTile
                label="Deepest candidate used"
                value={
                  retrieval.reranking.max_promoted_rank.maximum === null
                    ? "—"
                    : String(retrieval.reranking.max_promoted_rank.maximum)
                }
                detail={
                  retrieval.reranking.candidate_count.mean === null
                    ? undefined
                    : `of ${retrieval.reranking.candidate_count.mean.toFixed(0)} fetched`
                }
              />
              <StatTile
                label="Unused pool depth"
                value={
                  retrieval.reranking.unused_candidate_depth.mean === null
                    ? "—"
                    : retrieval.reranking.unused_candidate_depth.mean.toFixed(0)
                }
                detail="candidates scored but never selected"
              />
            </div>
          </div>
        )}
      </Panel>

      <Panel
        title="Errors"
        description={`${formatNumber(errors.failed_requests)} failed requests · ${formatPercent(
          errors.failure_rate,
          1,
        )}`}
      >
        {errors.by_stage.length === 0 ? (
          <EmptyState message="No stage errors in this window." />
        ) : (
          <table className="data-table mon-table">
            <thead>
              <tr>
                <th>Stage</th>
                <th>Error</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {errors.by_stage.map((row) => (
                <tr key={`${row.stage}-${row.error_type}`}>
                  <td>{row.stage.replace(/_/g, " ")}</td>
                  <td>{row.error_type}</td>
                  <td>{formatNumber(row.count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  );
}
