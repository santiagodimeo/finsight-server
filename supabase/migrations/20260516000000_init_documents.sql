-- Enable pgvector extension for embeddings
create extension if not exists vector;

-- Stores one record per ingested document (PDF, report, filing, etc.)
create table if not exists documents (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  source      text,                      -- file path or URL
  content     text,                      -- full extracted text
  metadata    jsonb not null default '{}',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Stores individual chunks with their embeddings
create table if not exists document_chunks (
  id           uuid primary key default gen_random_uuid(),
  document_id  uuid not null references documents(id) on delete cascade,
  chunk_index  integer not null,
  content      text not null,
  embedding    vector(1024),             -- voyage-finance-2 dimension
  metadata     jsonb not null default '{}',
  created_at   timestamptz not null default now()
);

-- IVFFlat index for fast approximate cosine similarity search
create index if not exists document_chunks_embedding_idx
  on document_chunks
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- Prevent duplicate chunks for the same document
create unique index if not exists document_chunks_doc_chunk_idx
  on document_chunks (document_id, chunk_index);
