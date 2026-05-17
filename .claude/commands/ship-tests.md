# Ship Tests

Write pytest tests for the essential business logic in `pipeline/` and `api/`.

## What to test

Focus on three modules only:

1. `pipeline/ingest.py` — `chunk_text` and `parse_csv` are pure functions (no mocks needed)
2. `pipeline/embed.py` — `embed_chunks` batching and retry logic (mock `pipeline.embed._get_client`)
3. `api/main.py` — `/upload` endpoint type validation and happy path (mock all pipeline functions)

## Rules

- Use `pytest` + `pytest-mock`
- All external clients (Voyage AI, Supabase, Anthropic) must be mocked — never hit real APIs
- Patch lazy singletons at the module level (e.g. `pipeline.embed._get_client`)
- No test should require `.env.local` or any real credentials
- Run `pytest tests/ -v` and confirm all tests pass before reporting done

## Structure

```
tests/
  __init__.py
  conftest.py       # shared fixtures
  test_ingest.py    # chunk_text + parse_csv
  test_embed.py     # embed_chunks batching + retry + embed_query
  test_api.py       # /upload validation
```

## Starting point

Read `pipeline/ingest.py`, `pipeline/embed.py`, and `api/main.py` before writing any tests.
Use the sample files in `docs/` as reference for realistic input shapes — but build synthetic
inputs in code so tests have no file dependencies.

## Cases to cover

### `chunk_text` (pipeline/ingest.py)
- empty string → `[]`
- text shorter than one chunk (10 words) → 1 chunk
- text exactly one chunk (384 words) → 1 chunk
- text one word over (385 words) → 2 chunks
- overlap correctness: last 48 words of chunk 1 == first 48 words of chunk 2
- custom `chunk_size` / `overlap` params respected

### `parse_csv` (pipeline/ingest.py)
- typical row: `date,amount,merchant` → `"date: 2024-03-01, amount: 42.50, merchant: Whole Foods"`
- empty values are filtered (blank field absent from output line)
- multi-row: 3 rows → 3 lines joined by `\n`

### `embed_chunks` / `embed_query` (pipeline/embed.py)
- single batch (5 chunks): `client.embed` called once, `input_type="document"`
- batch boundary (129 chunks): `client.embed` called twice (128 + 1)
- rate limit retry: first call raises `RateLimitError`, second succeeds → embeddings returned
- `embed_query`: `client.embed` called with `input_type="query"`

Patch target: `pipeline.embed._get_client` → mock returning `.embed()` configured per case.

### `/upload` (api/main.py)
- unsupported file type (`.txt`) → 422, detail contains "Unsupported"
- PDF accepted → 200, response has `document_id` and `chunk_count`
- CSV accepted → 200, response has `document_id` and `chunk_count`

Patch targets for happy path: `api.main.parse_pdf`, `api.main.parse_csv`,
`api.main.chunk_text`, `api.main.embed_chunks`, `api.main.upsert_document`,
`api.main.upsert_chunks`.
