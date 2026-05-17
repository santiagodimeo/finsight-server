alter table documents
  add column if not exists uploaded_by_client boolean not null default false;

create or replace function match_chunks(
  query_embedding text,
  match_count int default 5,
  client_only boolean default false
)
returns table (
  id uuid,
  document_id uuid,
  chunk_index integer,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql volatile as $$
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
    join documents d on dc.document_id = d.id
    where not client_only or d.uploaded_by_client = true
    order by dc.embedding <=> query_embedding::vector
    limit match_count;
end;
$$;
