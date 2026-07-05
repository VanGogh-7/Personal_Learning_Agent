export interface HealthResponse {
  status: string;
}

export interface StatusResponse {
  app_name: string;
  environment: string;
  version: string;
}

export interface RagQueryRequest {
  question: string;
  top_k: number;
  session_id?: string;
  include_long_term_memory: boolean;
}

export interface LibraryItemRagQueryRequest extends RagQueryRequest {
  library_item_id: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  document_title: string | null;
  chunk_index: number;
  content: string;
  char_start: number;
  char_end: number;
  score: number;
}

export interface RagMemoryMetadata {
  used_recent_turns: number;
  saved_current_turn: boolean;
  used_long_term_memories: number;
}

export interface RagQueryResponse {
  answer: string;
  retrieved_chunks: RetrievedChunk[];
  total_retrieved: number;
  session_id: string;
  memory: RagMemoryMetadata;
}

export interface RagLibraryItemMetadata {
  id: string;
  title: string;
  author: string | null;
  file_type: string | null;
  status: string;
}

export interface LibraryItemRagQueryResponse extends RagQueryResponse {
  library_item: RagLibraryItemMetadata;
}

export interface LongTermMemoryCreateRequest {
  memory_type: string;
  content: string;
  importance: number;
  source?: string | null;
  tags?: string[] | null;
}

export interface LongTermMemory {
  id: string;
  memory_type: string;
  content: string;
  importance: number;
  source: string | null;
  tags: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface LongTermMemoryListParams {
  memory_type?: string;
  min_importance?: number;
  limit?: number;
}

export interface LongTermMemorySearchParams extends LongTermMemoryListParams {
  keyword: string;
}

export interface LongTermMemoryListResponse {
  memories: LongTermMemory[];
  total: number;
}

export interface LibraryItem {
  id: string;
  title: string;
  author: string | null;
  description: string | null;
  file_path: string | null;
  file_type: string | null;
  topic_tags: string[] | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CreateLibraryItemPayload {
  title: string;
  author?: string | null;
  description?: string | null;
  file_path?: string | null;
  file_type?: string | null;
  topic_tags?: string[] | null;
  status?: string;
}

export interface UpdateLibraryItemPayload {
  title?: string;
  author?: string | null;
  description?: string | null;
  file_path?: string | null;
  file_type?: string | null;
  topic_tags?: string[] | null;
  status?: string;
}

export interface LibraryItemListParams {
  keyword?: string;
  status?: string;
  tag?: string;
  limit?: number;
}

export interface LibraryItemListResponse {
  items: LibraryItem[];
  total: number;
}

export interface LibraryItemIndexResponse {
  item_id: string;
  document_id?: string | null;
  status: string;
  chunks_created: number;
  embeddings_created: number;
  message: string;
  supported_file_types: string[];
}
