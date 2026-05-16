-- PostgREST cannot auto-cast JSON number arrays to vector(1024).
-- Accepting float8[] instead lets PostgREST map the JSON array natively,
-- then we cast to vector inside the function.
create or replace function match_chunks(
  query_embedding float8[],
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
