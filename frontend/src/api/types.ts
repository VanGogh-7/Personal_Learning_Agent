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

export interface MultiBookRagQueryRequest extends RagQueryRequest {
  library_item_ids: string[];
}

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

export interface SelectedLibraryItem extends RagLibraryItemMetadata {}

export interface MultiBookRagQueryResponse extends RagQueryResponse {
  selected_library_items: SelectedLibraryItem[];
}

export type AgentChatScopeType = "global" | "single_book" | "multi_book";

export interface AgentChatRequest extends RagQueryRequest {
  scope_type: AgentChatScopeType;
  library_item_id?: string | null;
  library_item_ids: string[];
}

export interface AgentChatResponse extends RagQueryResponse {
  scope_type: AgentChatScopeType;
  selected_library_items: SelectedLibraryItem[];
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

export interface LibraryMetadataDraft {
  library_item_id: string;
  title: string;
  summary: string;
  topic_tags: string[];
  chunks_used: number;
  mode: string;
}

export interface Note {
  id: string;
  title: string;
  content_latex: string;
  description: string | null;
  library_item_id: string | null;
  source_session_id: string | null;
  topic_tags: string[] | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface NoteCreateRequest {
  title: string;
  content_latex: string;
  description?: string | null;
  library_item_id?: string | null;
  source_session_id?: string | null;
  topic_tags?: string[] | null;
  status?: string;
}

export interface NoteUpdateRequest {
  title?: string;
  content_latex?: string;
  description?: string | null;
  library_item_id?: string | null;
  source_session_id?: string | null;
  topic_tags?: string[] | null;
  status?: string;
}

export interface NoteListParams {
  status?: string | null;
  library_item_id?: string | null;
  limit?: number;
  offset?: number;
}

export interface NoteSearchParams extends NoteListParams {
  keyword?: string;
}

export interface NoteListResponse {
  notes: Note[];
  total: number;
}

export interface ChatNoteChunkInput {
  id?: string | null;
  chunk_id?: string | null;
  document_id?: string | null;
  document_title?: string | null;
  chunk_index?: number | null;
  content: string;
  score?: number | null;
}

export interface ChatNoteLibraryItemInput {
  id: string;
  title: string;
  author?: string | null;
  file_type?: string | null;
  status?: string | null;
}

export interface ChatNoteDraftRequest {
  question: string;
  answer: string;
  retrieved_chunks: ChatNoteChunkInput[];
  library_item?: ChatNoteLibraryItemInput | null;
  session_id?: string | null;
}

export interface ChatNoteDraftResponse {
  title: string;
  content_latex: string;
  description?: string | null;
  library_item_id?: string | null;
  source_session_id?: string | null;
  topic_tags?: string[] | null;
}

export interface LearningEvent {
  id: string;
  event_type: string;
  title: string;
  description: string | null;
  source_type: string | null;
  source_id: string | null;
  library_item_id: string | null;
  note_id: string | null;
  session_id: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface LearningEventListResponse {
  events: LearningEvent[];
  total: number;
}

export interface LearningEventFilters {
  event_type?: string;
  source_type?: string;
  library_item_id?: string;
  note_id?: string;
  session_id?: string;
  limit?: number;
  offset?: number;
}

export interface LearningEventCreateRequest {
  event_type: string;
  title: string;
  description?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  library_item_id?: string | null;
  note_id?: string | null;
  session_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
}
