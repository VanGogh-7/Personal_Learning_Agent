export type HealthResponse = {
  status: string;
};

export type StatusResponse = {
  app_name: string;
  environment: string;
  version: string;
};

export type RagQueryRequest = {
  question: string;
  top_k: number;
  session_id?: string;
  include_long_term_memory: boolean;
};

export type RetrievedChunk = {
  chunk_id: string;
  document_id: string;
  document_title?: string | null;
  chunk_index: number;
  content: string;
  char_start: number;
  char_end: number;
  score: number;
};

export type RagMemoryMetadata = {
  used_recent_turns: number;
  saved_current_turn: boolean;
  used_long_term_memories: number;
};

export type RagQueryResponse = {
  answer: string;
  retrieved_chunks: RetrievedChunk[];
  total_retrieved: number;
  session_id: string;
  memory: RagMemoryMetadata;
};

export type LongTermMemoryCreateRequest = {
  memory_type: string;
  content: string;
  importance: number;
  source?: string | null;
  tags?: string[] | null;
};

export type LongTermMemory = {
  id: string;
  memory_type: string;
  content: string;
  importance: number;
  source?: string | null;
  tags?: string[] | null;
  created_at: string;
  updated_at: string;
};

export type LongTermMemoryListParams = {
  memory_type?: string;
  min_importance?: number;
  limit?: number;
};

export type LongTermMemorySearchParams = LongTermMemoryListParams & {
  keyword: string;
};

export type LongTermMemoryListResponse = {
  memories: LongTermMemory[];
  total: number;
};
