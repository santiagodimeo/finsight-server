-- float8[]::vector is not a valid pgvector cast.
-- Accept the vector as text (pgvector string format "[0.1,0.2,...]") and cast inside.
drop function if exists match_chunks(float8[], int);

create or replace function match_chunks(
  query_embedding text,
  match_count int default 5
)
returns table (
  id uuid,
  document_id uuid,
  chunk_index integer,
  content text,
  metadata jsonb,
  similarity float
)
language sql stable as $$
  select
    dc.id,
    dc.document_id,
    dc.chunk_index,
    dc.content,
    dc.metadata,
    1 - (dc.embedding <=> query_embedding::vector) as similarity
  from document_chunks dc
  order by dc.embedding <=> query_embedding::vector
  limit match_count;
$$;
