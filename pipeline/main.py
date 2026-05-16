"""
CLI entry point for the FinSight document processing pipeline.

Usage:
    python -m pipeline.main ingest <path>      Ingest a PDF or CSV file
    python -m pipeline.main search <query>     Run a semantic similarity search
"""

from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

import os
from pathlib import Path

import typer

from pipeline.embed import embed_chunks, embed_query
from pipeline.ingest import chunk_text, parse_csv, parse_pdf
from pipeline.store import similarity_search, upsert_chunks, upsert_document

app = typer.Typer(help="FinSight document ingestion pipeline.")


@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to a PDF or CSV file"),
    chunk_size: int = typer.Option(512, help="Token target per chunk"),
    overlap: int = typer.Option(64, help="Token overlap between consecutive chunks"),
) -> None:
    """Parse, chunk, embed, and store a document."""
    file = Path(path)
    if not file.exists():
        typer.echo(f"Error: file not found: {path}", err=True)
        raise typer.Exit(1)

    ext = file.suffix.lower()
    if ext == ".pdf":
        typer.echo(f"Parsing PDF: {file.name}")
        text = parse_pdf(path)
    elif ext == ".csv":
        typer.echo(f"Parsing CSV: {file.name}")
        text = parse_csv(path)
    else:
        typer.echo(f"Error: unsupported file type '{ext}' (use .pdf or .csv)", err=True)
        raise typer.Exit(1)

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    typer.echo(f"Chunked into {len(chunks)} segments")

    typer.echo("Embedding…")
    embeddings = embed_chunks(chunks)

    typer.echo("Storing…")
    doc_id = upsert_document(
        title=file.stem,
        source=str(file.resolve()),
        content=text,
        metadata={"file_name": file.name, "file_size": os.path.getsize(path)},
    )
    upsert_chunks(doc_id, chunks, embeddings)

    typer.echo(f"Done. Document ID: {doc_id}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language query"),
    top_k: int = typer.Option(5, help="Number of results to return"),
) -> None:
    """Run a semantic similarity search against stored document chunks."""
    typer.echo(f"Searching for: {query}\n")
    embedding = embed_query(query)
    results = similarity_search(embedding, top_k=top_k)

    if not results:
        typer.echo("No results found.")
        return

    for i, row in enumerate(results, 1):
        score = row.get("similarity", 0)
        preview = row["content"][:200].replace("\n", " ")
        typer.echo(f"[{i}] similarity={score:.4f}")
        typer.echo(f"    {preview}")
        typer.echo("")


if __name__ == "__main__":
    app()
