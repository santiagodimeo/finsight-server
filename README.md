# finsight-server

Python backend for FinSight — a RAG pipeline that ingests financial PDFs and CSVs, embeds them with Voyage AI, stores vectors in Supabase pgvector, and answers natural language questions via Claude.

Deployed as an AWS Lambda container image behind API Gateway HTTP API.

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI + Mangum (Lambda adapter) |
| Embeddings | Voyage AI `voyage-finance-2` (1024-dim) |
| Vector store | Supabase pgvector |
| PDF parsing | PyMuPDF |
| LLM | Anthropic Claude Haiku |
| Deploy | AWS Lambda (container) + API Gateway |

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload` | Upload a PDF or CSV — chunks, embeds, stores. Returns `document_id` and `chunk_count`. |
| `GET` | `/documents` | List all ingested documents. |
| `POST` | `/query` | Ask a question — retrieves relevant chunks, returns a Claude-generated answer. |

## Local setup

**Prerequisites:** Python 3.11+, a Supabase project with pgvector, Voyage AI key, Anthropic key.

```bash
git clone https://github.com/santiagodimeo/finsight-server.git
cd finsight-server

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env.local
# Fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, VOYAGE_API_KEY, ANTHROPIC_API_KEY
```

**Apply the database schema:**

```bash
npm install -g supabase   # or: brew install supabase/tap/supabase
supabase login
supabase link --project-ref <your-project-ref>
supabase db push
```

**Start the API server:**

```bash
uvicorn api.main:app --reload
# → http://localhost:8000
```

**Or use the CLI pipeline directly:**

```bash
python -m pipeline.main ingest path/to/statement.pdf
python -m pipeline.main ingest path/to/transactions.csv
python -m pipeline.main search "How much did I spend on groceries in March?"
```

## Environment variables

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (bypasses RLS) |
| `VOYAGE_API_KEY` | Voyage AI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |

Loaded from `.env.local` first, then `.env`. Values in `.env.local` take precedence.

## Running tests

Tests cover the core business logic (`chunk_text`, `parse_csv`, embed batching/retry, `/upload` validation). No real API credentials required — all external clients are mocked.

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Expected output: 16 tests, all passing.

## Deploying to AWS

**Prerequisites:** AWS CLI configured (`aws configure`), Docker running, `jq` installed, all four env vars set in `.env.local`.

```bash
bash infra/deploy.sh
```

The script is fully idempotent — safe to re-run on updates. It:

1. Creates an IAM execution role for Lambda
2. Creates an ECR repository
3. Builds a `linux/amd64` Docker image and pushes it to ECR
4. Creates or updates the Lambda function with your env vars
5. Creates an API Gateway HTTP API and wires up the routes

The deployed API URL is printed at the end:

```
✓ Deployed successfully.

  API URL: https://<id>.execute-api.us-east-1.amazonaws.com
```

## Testing on production

Replace `$API_URL` with your deployed API Gateway URL.

**List documents:**
```bash
curl $API_URL/documents
```

**Upload a file:**
```bash
curl -X POST $API_URL/upload \
  -F "file=@path/to/statement.pdf"
# → {"document_id": "...", "chunk_count": 42}
```

**Ask a question:**
```bash
curl -X POST $API_URL/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is my largest expense this month?"}'
# → {"answer": "...", "sources": [...]}
```

## Architecture

```
pipeline/ingest.py   parse_pdf / parse_csv → chunk_text → list[str]
pipeline/embed.py    embed_chunks / embed_query → list[list[float]]
pipeline/store.py    upsert_document / upsert_chunks / similarity_search
pipeline/main.py     Typer CLI wiring the three stages together
api/main.py          FastAPI endpoints — wraps the pipeline, adds Mangum handler
infra/deploy.sh      One-shot AWS deploy (IAM → ECR → Lambda → API Gateway)
tests/               pytest suite — pure unit tests + mocked API tests
```

**RAG flow in `/query`:**
1. Embed the question with Voyage AI (`input_type="query"`)
2. Run `similarity_search` → top-5 chunks via `match_chunks` Supabase RPC
3. Build a context string and prompt Claude Haiku
4. Return the answer and source snippets

**Chunking** uses a word-count approximation (0.75 words/token): 512 tokens → 384 words per chunk, 64-token overlap → 48 words.

**Parallel development with worktrees:**
```bash
bash scripts/wt.sh feature-name
# Creates ../finsight-server-worktrees/feature-name with .env and .claude/ copied in
```
