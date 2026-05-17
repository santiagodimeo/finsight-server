-- IVFFlat with lists=100 but few rows causes empty results because the default
-- probes=1 only searches 1 cluster. Setting probes=lists ensures every cluster
-- is searched (full scan), which is correct for small datasets and still
-- benefits from the index when the dataset grows.
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
language plpgsql stable as $$
begin
  set local ivfflat.probes = 100;
  return query
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
end;
$$;
