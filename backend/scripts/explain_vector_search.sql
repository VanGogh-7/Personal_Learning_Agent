-- Run with psql variables containing a 2048-dimensional vector and UUID array:
-- psql "$DATABASE_URL" -v query_embedding='[0,...]' \
--   -v document_ids='{uuid-1,uuid-2}' -f scripts/explain_vector_search.sql

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    document_chunks.*,
    document_chunks.embedding <-> CAST(:'query_embedding' AS vector) AS distance
FROM document_chunks
WHERE document_chunks.document_id = ANY(CAST(:'document_ids' AS uuid[]))
  AND document_chunks.embedding IS NOT NULL
  AND document_chunks.section_type NOT IN (
      'contents',
      'index',
      'bibliography',
      'preface'
  )
ORDER BY document_chunks.embedding <-> CAST(:'query_embedding' AS vector)
LIMIT 5;
