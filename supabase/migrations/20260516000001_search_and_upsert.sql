create unique index if not exists documents_source_idx on documents (source);

create or replace function match_chunks(
  query_embedding vector(1024),
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
    1 - (dc.embedding <=> query_embedding) as similarity
  from document_chunks dc
  order by dc.embedding <=> query_embedding
  limit match_count;
$$;
