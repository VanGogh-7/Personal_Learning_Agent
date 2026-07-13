-- Run with a 1024-dimensional vector, active index-version UUID, and UUID array:
-- psql "$DATABASE_URL" -v query_embedding='[0,...]' \
--   -v index_version_id='uuid' -v document_ids='{uuid-1,uuid-2}' \
--   -f scripts/explain_vector_search.sql

-- Selected-book exact plan. The application takes this path for at most
-- LOCAL_EXACT_SEARCH_MAX_DOCUMENTS documents and fuses it with FTS results.
BEGIN;
SET LOCAL enable_indexscan = off;
SET LOCAL enable_bitmapscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    document_chunks.*,
    chunk_embeddings.embedding <-> CAST(:'query_embedding' AS vector(1024)) AS distance
FROM document_chunks
JOIN chunk_embeddings ON chunk_embeddings.chunk_id = document_chunks.id
WHERE document_chunks.document_id = ANY(CAST(:'document_ids' AS uuid[]))
  AND chunk_embeddings.index_version_id = CAST(:'index_version_id' AS uuid)
  AND chunk_embeddings.embedding IS NOT NULL
  AND document_chunks.section_type NOT IN (
      'contents',
      'index',
      'bibliography',
      'preface'
  )
ORDER BY chunk_embeddings.embedding <-> CAST(:'query_embedding' AS vector(1024))
LIMIT 5;

RESET enable_indexscan;
RESET enable_bitmapscan;

-- Whole-library ANN plan. hnsw.ef_search is request-local in the application.
SET LOCAL hnsw.ef_search = 40;
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    document_chunks.*,
    chunk_embeddings.embedding <-> CAST(:'query_embedding' AS vector(1024)) AS distance
FROM chunk_embeddings
JOIN document_chunks ON document_chunks.id = chunk_embeddings.chunk_id
WHERE chunk_embeddings.index_version_id = CAST(:'index_version_id' AS uuid)
  AND chunk_embeddings.embedding IS NOT NULL
  AND document_chunks.section_type NOT IN (
      'contents',
      'index',
      'bibliography',
      'preface'
  )
ORDER BY chunk_embeddings.embedding <-> CAST(:'query_embedding' AS vector(1024))
LIMIT 5;

COMMIT;
