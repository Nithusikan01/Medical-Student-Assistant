export interface SourceMetadata {
  document_id: string;
  filename: string;
  source_path: string;
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
  sources: SourceChunk[];
  processing_time_ms: number | null;
}

export interface IngestResponse {
  filename: string;
  status: string;
  message: string;
}
