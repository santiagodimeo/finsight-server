"""
Voyage AI embedding layer.

Responsibilities:
- Wrap the voyageai client for voyage-finance-2
- Batch chunks to stay within API rate limits (128 items per request)
- Return float32 embedding vectors (1024 dimensions)
"""

import os
import time

import voyageai
from voyageai.error import RateLimitError

_client: voyageai.Client | None = None

_MODEL = "voyage-finance-2"
_BATCH_SIZE = voyageai.VOYAGE_EMBED_BATCH_SIZE


def _get_client() -> voyageai.Client:
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    return _client


def _embed_with_retry(
    texts: list[str], input_type: str, max_retries: int = 5
) -> list[list[float]]:
    client = _get_client()
    delay = 20
    for attempt in range(max_retries):
        try:
            result = client.embed(texts, model=_MODEL, input_type=input_type)
            return result.embeddings
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            print(f"Rate limited — retrying in {delay}s…")
            time.sleep(delay)
            delay *= 2
    return []  # unreachable


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed a list of text chunks using voyage-finance-2."""
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[i : i + _BATCH_SIZE]
        embeddings.extend(_embed_with_retry(batch, input_type="document"))
    return embeddings


def embed_query(query: str) -> list[float]:
    """Embed a single query string for similarity search."""
    return _embed_with_retry([query], input_type="query")[0]
