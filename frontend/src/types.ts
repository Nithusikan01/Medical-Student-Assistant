export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: "user" | "admin";
  is_active: boolean;
  has_password: boolean;
  has_google: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface SourceMetadata {
  document_id: string;
  filename: string;
  page_number: number | null;
  section_title: string | null;
  heading_level: number | null;
  chunk_index: number;
  start_char: number | null;
  end_char: number | null;
  language: string | null;
  tags: string[];
}

export interface SourceChunk {
  id: string;
  score: number;
  retrieval_method: string | null;
  rerank_score: number | null;
  text: string;
  preview: string | null;
  metadata: SourceMetadata;
}

export interface QueryResponse {
  conversation_id: string;
  question: string;
  answer: string;
  model: string;
  sources: SourceChunk[];
  processing_time_ms: number | null;
  // The stored id of this answer, so it can be rated without reloading the
  // conversation. Null means rating is unavailable for this one.
  message_id: number | null;
}

export interface GenerationModelInfo {
  id: string;
  label: string;
  provider: string;
}

export interface GenerationModelsResponse {
  models: GenerationModelInfo[];
  default: string;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string | null;
  message_count: number;
}

export type FeedbackRating = "up" | "down";

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: SourceChunk[] | null;
  created_at: string;
  // This reader's own rating, so reopening a conversation restores it.
  feedback: FeedbackRating | null;
}

export interface FeedbackResponseBody {
  message_id: number;
  rating: FeedbackRating;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string | null;
  messages: ConversationMessage[];
}

export interface AdminUserSummary {
  id: string;
  email: string;
  full_name: string | null;
  role: "user" | "admin";
  is_active: boolean;
  created_at: string;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  status: "processing" | "ready" | "failed" | "deleting";
  error: string | null;
  page_count: number | null;
  chunk_count: number;
  size_bytes: number | null;
  uploaded_by_email: string | null;
  created_at: string;
}

export interface IngestResponse {
  filename: string;
  status: string;
  message: string;
  document: DocumentSummary | null;
}

export interface ModelUsageInfo {
  id: string;
  label: string;
  provider: string;
  daily_tokens_used: number;
  daily_token_limit: number | null;
  monthly_tokens_used: number;
  monthly_token_limit: number | null;
  // Serialised as a decimal string. null means no pricing is configured for
  // this model, which is not the same as costing nothing - render it as
  // "not priced", never as $0.00.
  daily_estimated_cost_usd: string | null;
  monthly_estimated_cost_usd: string | null;
}

export interface StageUsageInfo {
  stage: string;
  tokens_used: number;
}

export interface ModelUsageResponse {
  models: ModelUsageInfo[];
  // Today's tokens by pipeline stage. Answers "why did consumption go up",
  // not just "by how much".
  stages: StageUsageInfo[];
  pricing_configured: boolean;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// Monitoring
//
// Mirrors backend/src/backend/schemas/monitoring.py by hand, like the rest of
// this file. Two conventions carry through and change how these render:
//
//   - null is not zero. An absent percentile means nothing ran, not that it
//     was instant; a null cost means the model is not priced, not free.
//   - nothing here is a quality claim. Recall@K, faithfulness and the rest
//     need ground truth the API does not have.
//
// Decimal fields arrive as strings, so they survive the JSON round trip
// without losing precision to a float.
// ---------------------------------------------------------------------------

export type MonitoringRange = "15m" | "1h" | "6h" | "24h" | "7d" | "30d";

export interface WindowInfo {
  start: string;
  end: string;
  range: string | null;
  bucket_seconds: number;
}

export interface LatencyInfo {
  count: number;
  p50_ms: number | null;
  p75_ms: number | null;
  p90_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
}

export interface RequestInfo {
  total: number;
  succeeded: number;
  client_errors: number;
  failed: number;
  success_rate: number;
  client_error_rate: number;
  failure_rate: number;
  requests_per_minute: number;
  latency: LatencyInfo;
}

export interface StageLatencyInfo {
  stage: string;
  count: number;
  errors: number;
  error_rate: number;
  latency: LatencyInfo;
}

export interface SeriesPointInfo {
  start: string;
  total: number;
  succeeded: number;
  client_errors: number;
  failed: number;
  p95_ms: number | null;
}

export interface InFlightInfo {
  current: number;
  peak: number;
  // Always true: a trace row is written only when a request finishes, so
  // this comes from the process, not the database. With several tasks
  // running it is one task's share - say so rather than imply a total.
  per_process: boolean;
}

export interface RouteCountInfo {
  route: string;
  count: number;
}

export interface OverviewResponse {
  window: WindowInfo;
  requests: RequestInfo;
  slowest_stages: StageLatencyInfo[];
  in_flight: InFlightInfo;
  total_tokens: number;
  estimated_cost_usd: string | null;
  pricing_configured: boolean;
  error_count: number;
}

export interface PerformanceResponse {
  window: WindowInfo;
  requests: RequestInfo;
  stages: StageLatencyInfo[];
  series: SeriesPointInfo[];
  routes: RouteCountInfo[];
}

export interface ModelSpendInfo {
  model_id: string;
  provider: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: string | null;
  priced_calls: number;
}

export interface StageSpendInfo {
  stage: string;
  calls: number;
  total_tokens: number;
  estimated_cost_usd: string | null;
}

export interface TokensResponse {
  window: WindowInfo;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: string | null;
  pricing_configured: boolean;
  by_model: ModelSpendInfo[];
  by_stage: StageSpendInfo[];
}

export interface DistributionInfo {
  count: number;
  mean: number | null;
  p50: number | null;
  p95: number | null;
  minimum: number | null;
  maximum: number | null;
}

export interface RetrieverInfo {
  stage: string;
  calls: number;
  empty_calls: number;
  empty_rate: number;
  result_count: DistributionInfo;
  top_score: DistributionInfo;
  average_score: DistributionInfo;
}

export interface FusionInfo {
  calls: number;
  dense_only_share: number | null;
  bm25_only_share: number | null;
  overlap_share: number | null;
  single_retriever_calls: number;
  single_retriever_rate: number;
  overlap_count: DistributionInfo;
  unique_count: DistributionInfo;
}

export interface RerankingInfo {
  calls: number;
  reranker_usage: Record<string, number>;
  degraded_calls: number;
  degraded_rate: number;
  changed_calls: number;
  change_rate: number;
  candidate_count: DistributionInfo;
  final_count: DistributionInfo;
  introduced_count: DistributionInfo;
  reordered_count: DistributionInfo;
  top_score: DistributionInfo;
  max_promoted_rank: DistributionInfo;
  mean_promoted_rank: DistributionInfo;
  unused_candidate_depth: DistributionInfo;
}

export interface RetrievalResponse {
  window: WindowInfo;
  retrievers: RetrieverInfo[];
  // null means the stage did not run, which is not the same as running and
  // finding nothing.
  fusion: FusionInfo | null;
  reranking: RerankingInfo | null;
  offline_metrics_available: boolean;
  offline_metrics_note: string;
}

export interface ErrorCountInfo {
  stage: string;
  error_type: string;
  count: number;
}

export interface ErrorCategoryInfo {
  category: string;
  stage: string;
  count: number;
}

export interface ErrorsResponse {
  window: WindowInfo;
  failed_requests: number;
  failure_rate: number;
  by_stage: ErrorCountInfo[];

  // What to do about it, as opposed to which exception class was raised.
  by_category: ErrorCategoryInfo[];
  category_totals: Record<string, number>;

  // Null means no provider offered one, which is not "retry now".
  max_retry_after_seconds: number | null;
}

export interface KnowledgeBaseInfo {
  documents_by_status: Record<string, number>;
  total_documents: number;
  ready_documents: number;

  chunks_stored: number;
  chunks_retrievable: number;

  // Stored, vectors live, but invisible to lexical search because the
  // document is not ready. Zero is the healthy value.
  chunks_unreachable: number;

  last_ingested_at: string | null;
  stalled_documents: number;
  healthy: boolean;
}

export interface IngestionResponse {
  window: WindowInfo;
  knowledge_base: KnowledgeBaseInfo;
  stages: StageLatencyInfo[];
  ingestions: number;
  failed_ingestions: number;
  stall_threshold_minutes: number;
}

export interface NegativeFeedbackInfo {
  message_id: number;
  conversation_id: string;
  created_at: string;
  comment: string | null;
  trace_id: string | null;
}

export interface FeedbackSummaryResponse {
  window: WindowInfo;
  up: number;
  down: number;
  total: number;
  answers: number;
  // Null when nobody rated anything. A share of nothing is undefined, and
  // 0% would read as "everyone hated it".
  response_rate: number | null;
  positive_rate: number | null;
  recent_negative: NegativeFeedbackInfo[];
}

export interface TraceSummaryInfo {
  trace_id: string;
  request_id: string | null;
  route: string | null;
  status: string;
  status_code: number | null;
  error_type: string | null;
  started_at: string;
  duration_ms: number;
  conversation_id: string | null;
  user_id: string | null;
  environment: string | null;
  app_version: string | null;
}

export interface TraceListResponse {
  window: WindowInfo;
  traces: TraceSummaryInfo[];
  // Pass back as `before` for the next page. null on the last page.
  next_before: string | null;
}

export interface SpanInfo {
  span_id: string;
  parent_span_id: string | null;
  // Waterfall position. Order by this, never by started_at - the wall clock
  // ties between a parent span and the child it opens.
  sequence: number;
  stage: string;
  status: string;
  error_type: string | null;
  started_at: string;
  duration_ms: number;
  metadata: Record<string, unknown>;
}

export interface TraceTokenInfo {
  stage: string;
  model_id: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: string | null;
}

export interface TraceDetailResponse {
  trace: TraceSummaryInfo;
  spans: SpanInfo[];
  tokens: TraceTokenInfo[];
  total_tokens: number;
  estimated_cost_usd: string | null;
}
