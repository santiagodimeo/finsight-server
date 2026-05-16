# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# finsight-server

Python backend for FinSight — document ingestion pipeline + future FastAPI server.

## What this does

Ingests financial PDFs and CSVs (10-Ks, earnings reports, pay stubs, bank statements), chunks them, embeds with Voyage AI's `voyage-finance-2` model, and stores results in Supabase pgvector for semantic retrieval.

## Stack

- **Language**: Python 3.11+
- **Embeddings**: Voyage AI `voyage-finance-2` (1024-dim, finance-tuned)
- **Vector store**: Supabase + pgvector
- **PDF parsing**: PyMuPDF (fitz)
- **CLI**: Typer
- **Future API**: FastAPI + Uvicorn (only `api/__init__.py` exists; not yet implemented)

## Running the pipeline

```bash
cp .env.example .env.local   # fill in keys
pip install -r requirements.txt
python -m pipeline.main ingest path/to/report.pdf
python -m pipeline.main ingest path/to/data.csv
python -m pipeline.main search "what was Q3 revenue?"
```

`--chunk-size` and `--overlap` are optional flags on the `ingest` command (defaults: 512 tokens, 64-token overlap).

## Environment variables

Loaded in order: `.env.local` first, then `.env`. Values in `.env.local` take precedence.

| Variable                   | Description                        |
|----------------------------|------------------------------------|
| `SUPABASE_URL`             | Your Supabase project URL          |
| `SUPABASE_SERVICE_ROLE_KEY`| Service role key (bypasses RLS)    |
| `VOYAGE_API_KEY`           | Voyage AI API key                  |

## Architecture

The pipeline is four sequential stages, each in its own module:

```
pipeline/ingest.py   parse_pdf / parse_csv → chunk_text → list[str]
pipeline/embed.py    embed_chunks / embed_query → list[list[float]]
pipeline/store.py    upsert_document / upsert_chunks / similarity_search
pipeline/main.py     Typer CLI wiring the three stages together
```

**Chunking** uses a word-count approximation (0.75 words/token ratio), not a real tokenizer. 512 tokens ≈ 384 words; 64-token overlap ≈ 48 words.

**CSV ingestion** serialises each row as `"col: value, col: value"` so column names are preserved as context for the embedding model.

**Embedding** batches to `voyageai.VOYAGE_EMBED_BATCH_SIZE` (128) with exponential-backoff retry on rate limit errors. Chunks use `input_type="document"`; queries use `input_type="query"`.

**Deduplication**: `documents` upserts on `source` (resolved file path); `document_chunks` upserts on `(document_id, chunk_index)`.

## Supabase schema

- `documents` — one row per ingested document
- `document_chunks` — one row per chunk, with `embedding vector(1024)` and IVFFlat cosine index (lists=100)
- `match_chunks(query_embedding text, match_count int)` RPC — accepts the embedding as a pgvector text literal `"[0.1,0.2,...]"` and casts to `vector` internally. This is intentional: PostgREST cannot auto-cast JSON arrays or `float8[]` to `vector(1024)`, so the Python client serialises the vector to a bracketed string before calling `.rpc()`.

Migrations are in `supabase/migrations/` and managed via Supabase CLI. Supabase project ref: `chiebawikojfnhrrnjrf`.

## Constraints

- Chunk size target: 512 tokens, 64-token overlap
- `voyage-finance-2` max input: 32,000 tokens per chunk
- Embeddings are 1024-dimensional float32 vectors
