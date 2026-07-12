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
  source_type?: "local";
  title?: string | null;
  url?: string | null;
  section_path?: string[];
  authors?: string[];
  published_at?: string | null;
  doi?: string | null;
  arxiv_id?: string | null;
  extraction_method?: string | null;
  ocr_confidence?: number | null;
  bounding_boxes?: Array<Record<string, unknown>>;
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
  conversation_id?: string;
  selected_library_item_id?: string | null;
  selected_library_item_ids?: string[];
}

export interface AgentChatResponse extends Omit<
  RagQueryResponse,
  "session_id"
> {
  conversation_id: string;
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
  citation_id?: string | null;
  title: string;
  url: string;
  excerpt: string;
  provider: string;
  published_date?: string | null;
  published_at?: string | null;
  retrieved_at?: string | null;
  evidence_id?: string | null;
  source_type?: "web" | "news" | "academic" | "page";
  content?: string | null;
  authors?: string[];
  doi?: string | null;
  arxiv_id?: string | null;
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

export type ProviderKind = "chat" | "embedding";
export type ProviderId =
  | "deepseek"
  | "openai"
  | "openai_compatible"
  | "anthropic"
  | "gemini"
  | "zhipu"
  | "ollama"
  | "custom_openai_compatible";

export interface ProviderCapabilities {
  chat: boolean;
  streaming: boolean;
  tool_calling: boolean;
  structured_output: boolean;
  embeddings: boolean;
  multimodal_input: boolean;
  native_adapter: boolean;
}

export interface ProviderCatalogEntry {
  provider: ProviderId;
  label: string;
  capabilities: ProviderCapabilities;
  default_chat_base_url?: string | null;
  default_embedding_base_url?: string | null;
  requires_api_key: boolean;
  runtime_status: "available" | "extension_ready";
}

export interface ProviderProfileInput {
  kind: ProviderKind;
  name: string;
  provider: ProviderId;
  api_key?: string | null;
  secret_ref?: string | null;
  base_url: string;
  model: string;
  temperature?: number | null;
  max_output_tokens?: number | null;
  embedding_dimension?: number | null;
  batch_size?: number | null;
  extra_headers?: Record<string, string>;
}

export interface ProviderProfile extends Omit<ProviderProfileInput, "api_key"> {
  id: string;
  api_key_configured: boolean;
  api_key_mask?: string | null;
  config_version: number;
  is_active: boolean;
  runtime_active: boolean;
}

export interface ProviderProfileList {
  profiles: ProviderProfile[];
  active_chat_profile?: string | null;
  active_embedding_profile?: string | null;
}

export interface ProviderConnectionTest {
  success: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  capabilities: ProviderCapabilities;
  actual_embedding_dimension?: number | null;
  message: string;
}
