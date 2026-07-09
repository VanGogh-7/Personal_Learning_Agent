export interface RagCitation {
  citation_id: string;
  chunk_id: string;
  document_id: string;
  library_item_id: string | null;
  library_title: string | null;
  library_author: string | null;
  document_title: string | null;
  document_source_path: string | null;
  chunk_index: number;
  page_number: number | null;
  page_start: number | null;
  page_end: number | null;
  section_type?: string | null;
  chapter_title?: string | null;
  section_title?: string | null;
  score: number;
  excerpt: string;
  content: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  document_title: string | null;
  document_source_path: string | null;
  chunk_index: number;
  page_number: number | null;
  page_start: number | null;
  page_end: number | null;
  section_type?: string | null;
  chapter_title?: string | null;
  section_title?: string | null;
  content: string;
  char_start: number;
  char_end: number;
  score: number;
  citation: RagCitation;
}

export interface RagMemoryMetadata {
  used_recent_turns: number;
  saved_current_turn: boolean;
  used_long_term_memories: number;
}

export interface RagQueryResponse {
  answer: string;
  retrieved_chunks: RetrievedChunk[];
  citations: RagCitation[];
  total_retrieved: number;
  session_id: string;
  memory: RagMemoryMetadata;
}

export interface SelectedLibraryItem {
  id: string;
  title: string;
  author: string | null;
  file_type: string | null;
  status: string;
}

export type AgentChatScopeType = "global" | "single_book" | "multi_book";
export type AgentChatRoute = "local_only" | "web_only" | "both";

export interface AgentChatRequest {
  message: string;
  selected_library_item_id?: string | null;
  selected_library_item_ids?: string[];
}

export interface AgentChatResponse extends RagQueryResponse {
  scope_type: AgentChatScopeType;
  route: AgentChatRoute;
  selected_library_items: SelectedLibraryItem[];
  local_citations?: RagCitation[];
  web_sources?: WebSource[];
  warnings?: string[];
  errors?: string[];
  local_summary?: string | null;
  web_summary?: string | null;
}

export interface WebSource {
  source_id: string;
  title: string;
  url: string;
  excerpt: string;
  provider: string;
  published_date?: string | null;
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

export interface LibraryPdfImportRequest {
  source_paths: string[];
}

export interface LibraryPdfImportItemResponse {
  library_item: LibraryItem;
  index_result: LibraryItemIndexResponse;
  original_filename: string;
  original_source_path: string;
  managed_file_path: string;
  file_size_bytes: number;
}

export interface LibraryPdfImportResponse {
  items: LibraryPdfImportItemResponse[];
  total: number;
}
