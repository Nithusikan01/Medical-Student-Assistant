import type {
  ErrorsResponse,
  IngestionResponse,
  MonitoringRange,
  OverviewResponse,
  PerformanceResponse,
  RetrievalResponse,
  TokensResponse,
  TraceDetailResponse,
  TraceListResponse,
} from "../types";
import { request } from "./client";

export interface WindowParams {
  range?: MonitoringRange;
  // An explicit pair overrides `range`. ISO 8601; a bare timestamp is read
  // as UTC by the API.
  start?: string;
  end?: string;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }

  const rendered = search.toString();

  return rendered ? `?${rendered}` : "";
}

export function getOverview(params: WindowParams = {}): Promise<OverviewResponse> {
  return request<OverviewResponse>(`/api/monitoring/overview${query({ ...params })}`);
}

export function getPerformance(
  params: WindowParams & { route?: string } = {},
): Promise<PerformanceResponse> {
  return request<PerformanceResponse>(
    `/api/monitoring/performance${query({ ...params })}`,
  );
}

export function getTokens(params: WindowParams = {}): Promise<TokensResponse> {
  return request<TokensResponse>(`/api/monitoring/tokens${query({ ...params })}`);
}

export function getRetrieval(params: WindowParams = {}): Promise<RetrievalResponse> {
  return request<RetrievalResponse>(`/api/monitoring/retrieval${query({ ...params })}`);
}

export function getErrors(params: WindowParams = {}): Promise<ErrorsResponse> {
  return request<ErrorsResponse>(`/api/monitoring/errors${query({ ...params })}`);
}

export function getIngestion(params: WindowParams = {}): Promise<IngestionResponse> {
  return request<IngestionResponse>(`/api/monitoring/ingestion${query({ ...params })}`);
}

export function listTraces(
  params: WindowParams & {
    limit?: number;
    // Cursor from a previous page's `next_before`. Null there means this
    // was the last page.
    before?: string;
    route?: string;
    failed_only?: boolean;
    conversation_id?: string;
  } = {},
): Promise<TraceListResponse> {
  return request<TraceListResponse>(`/api/monitoring/traces${query({ ...params })}`);
}

export function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return request<TraceDetailResponse>(
    `/api/monitoring/traces/${encodeURIComponent(traceId)}`,
  );
}
