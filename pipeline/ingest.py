"""
Document parsing and chunking.

Responsibilities:
- Extract raw text from PDF files (via pymupdf)
- Extract raw text from CSV files (preserving column names for LLM context)
- Split text into overlapping chunks sized for voyage-finance-2
- Return structured chunk objects ready for embedding
"""

import csv

import fitz


def parse_pdf(file_path: str) -> str:
    """Extract full text from a PDF file."""
    doc = fitz.open(file_path)
    return "\n".join(page.get_text() for page in doc)


def parse_csv(file_path: str) -> str:
    """Extract text from a CSV file, preserving column names as context."""
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            ", ".join(f"{k}: {v}" for k, v in row.items() if v)
            for row in reader
        ]
    return "\n".join(rows)


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Split text into overlapping chunks by approximate token count.

    Uses 0.75 words-per-token ratio: 512 tokens ≈ 384 words, 64-token overlap ≈ 48 words.
    """
    words_per_chunk = int(chunk_size * 0.75)
    words_overlap = int(overlap * 0.75)
    step = words_per_chunk - words_overlap

    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start : start + words_per_chunk]).strip()
        if chunk:
            chunks.append(chunk)
        start += step

    return chunks
