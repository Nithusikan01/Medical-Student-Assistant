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

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: SourceChunk[] | null;
  created_at: string;
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
