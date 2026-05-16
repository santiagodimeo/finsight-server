"""
Supabase persistence layer.

Responsibilities:
- Upsert documents and their chunks into Supabase
- Run pgvector similarity search against document_chunks via match_chunks RPC
- Return ranked results with source metadata
"""

import os

from supabase import Client, create_client

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _client


def upsert_document(title: str, source: str, content: str, metadata: dict) -> str:
    """Insert or update a document record. Returns the document UUID."""
    client = _get_client()
    result = (
        client.table("documents")
        .upsert(
            {"title": title, "source": source, "content": content, "metadata": metadata},
            on_conflict="source",
        )
        .execute()
    )
    return result.data[0]["id"]


def upsert_chunks(
    document_id: str, chunks: list[str], embeddings: list[list[float]]
) -> None:
    """Batch upsert chunks and their embeddings for a document."""
    client = _get_client()
    rows = [
        {
            "document_id": document_id,
            "chunk_index": i,
            "content": chunk,
            "embedding": embedding,
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    client.table("document_chunks").upsert(
        rows, on_conflict="document_id,chunk_index"
    ).execute()


def similarity_search(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """Find the top_k most similar chunks using cosine distance."""
    client = _get_client()
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    result = client.rpc(
        "match_chunks",
        {"query_embedding": vec_str, "match_count": top_k},
    ).execute()
    return result.data
