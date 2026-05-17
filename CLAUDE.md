# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# finsight-server

Python backend for FinSight — document ingestion pipeline and FastAPI server deployed as an AWS Lambda container.

## What this does

Ingests financial PDFs and CSVs (10-Ks, earnings reports, pay stubs, bank statements), chunks them, embeds with Voyage AI's `voyage-finance-2` model, and stores results in Supabase pgvector for semantic retrieval. Exposes a RAG API that answers natural language questions over uploaded documents using Claude.

## Stack

- **Language**: Python 3.11+
- **Embeddings**: Voyage AI `voyage-finance-2` (1024-dim, finance-tuned)
- **Vector store**: Supabase + pgvector
- **PDF parsing**: PyMuPDF (fitz)
- **API**: FastAPI + Uvicorn, wrapped in Mangum for Lambda
- **LLM**: Anthropic Claude (`claude-haiku-4-5-20251001`) for `/query` responses
- **CLI**: Typer
- **Deploy**: AWS Lambda (container image via ECR) + API Gateway HTTP API

## Running locally

```bash
cp .env.example .env.local   # fill in keys
pip install -r requirements.txt

# Start the API server
uvicorn api.main:app --reload

# Or use the CLI pipeline directly
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
| `ANTHROPIC_API_KEY`        | Anthropic API key (used by `/query`)|

## API endpoints

| Method | Path          | Description                                       |
|--------|---------------|---------------------------------------------------|
| POST   | `/upload`     | Upload a PDF or CSV; returns `document_id`, `chunk_count` |
| GET    | `/documents`  | List all ingested documents (id, title, source, created_at) |
| POST   | `/query`      | RAG: embed question → search chunks → Claude answer |

The `/query` endpoint takes `{"question": "..."}` and returns `{"answer": "...", "sources": [...]}`.

## Architecture

### Pipeline (ingestion)

```
pipeline/ingest.py   parse_pdf / parse_csv → chunk_text → list[str]
pipeline/embed.py    embed_chunks / embed_query → list[list[float]]
pipeline/store.py    upsert_document / upsert_chunks / similarity_search
pipeline/main.py     Typer CLI wiring the three stages together
```

### API (`api/main.py`)

Imports the same pipeline modules and wraps them in FastAPI endpoints. Uses module-level lazy singletons (`_supabase`, `_anthropic`) initialised on first request so Lambda cold-start doesn't fail if env vars are missing at import time. The `handler = Mangum(app)` export is the Lambda entrypoint.

### RAG flow in `/query`

1. Embed the question with `embed_query` (Voyage `input_type="query"`)
2. Call `similarity_search` → top-5 chunks via `match_chunks` RPC
3. Build a context string and prompt Claude Haiku with it
4. Return the answer and truncated source snippets

### Key implementation details

**Chunking** uses a word-count approximation (0.75 words/token ratio), not a real tokenizer. 512 tokens ≈ 384 words; 64-token overlap ≈ 48 words.

**CSV ingestion** serialises each row as `"col: value, col: value"` so column names are preserved as context for the embedding model.

**Embedding** batches to `voyageai.VOYAGE_EMBED_BATCH_SIZE` (128) with exponential-backoff retry on rate limit errors. Chunks use `input_type="document"`; queries use `input_type="query"`.

**Deduplication**: `documents` upserts on `source` (resolved file path); `document_chunks` upserts on `(document_id, chunk_index)`.

**Vector serialisation**: `similarity_search` serialises the embedding as a bracketed string `"[0.1,0.2,...]"` before calling `.rpc("match_chunks", ...)`. PostgREST cannot auto-cast JSON arrays or `float8[]` to `vector(1024)`, so `match_chunks` accepts `text` and casts internally.

## Supabase schema

- `documents` — one row per ingested document
- `document_chunks` — one row per chunk, with `embedding vector(1024)` and IVFFlat cosine index (lists=100)
- `match_chunks(query_embedding text, match_count int)` RPC — must be `VOLATILE` (not stable/immutable) so Postgres doesn't cache results; a `SET ivfflat.probes = 100` inside the function ensures the index is actually searched

Migrations are in `supabase/migrations/` and managed via Supabase CLI. Supabase project ref: `chiebawikojfnhrrnjrf`.

To push a new migration:
```bash
supabase db push
```

## Parallel development (git worktrees)

`scripts/wt.sh` creates an isolated worktree for a new branch so you can run multiple Claude Code sessions side-by-side without switching branches.

```bash
bash scripts/wt.sh <branch-name>
```

The worktree is created at `../finsight-server-worktrees/<branch-name>` (sibling to this repo). Your `.env` and `.claude/` folder are copied automatically.

Optional shell alias (add to `~/.zshrc` pointing at your local clone):

```bash
alias wts='bash /your/path/to/finsight-server/scripts/wt.sh'
```

Then just run `wts feature-name` from anywhere.

## Deployment

The app runs as an AWS Lambda container image behind API Gateway. The deploy script handles everything idempotently:

```bash
bash infra/deploy.sh
```

Prerequisites: AWS CLI configured, Docker running, `jq` installed, and all four env vars set in `.env.local`. The script creates/updates the IAM role, ECR repo, Lambda function, and API Gateway HTTP API. Docker image must be built for `linux/amd64`.

## Constraints

- Chunk size target: 512 tokens, 64-token overlap
- `voyage-finance-2` max input: 32,000 tokens per chunk
- Embeddings are 1024-dimensional float32 vectors
- `numpy<2` pinned (voyageai SDK compatibility)
