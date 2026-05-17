import io
import textwrap

import pytest

from pipeline.ingest import chunk_text, parse_csv

# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

WORDS_PER_CHUNK = int(512 * 0.75)   # 384
WORDS_OVERLAP   = int(64  * 0.75)   # 48
STEP            = WORDS_PER_CHUNK - WORDS_OVERLAP  # 336


def _words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_chunk_text_shorter_than_one_chunk():
    result = chunk_text(_words(10))
    assert len(result) == 1
    assert result[0].split() == [f"word{i}" for i in range(10)]


def test_chunk_text_exactly_one_chunk():
    # One chunk only when len(words) <= STEP (336); the loop doesn't re-fire.
    result = chunk_text(_words(STEP))
    assert len(result) == 1
    assert len(result[0].split()) == STEP


def test_chunk_text_one_word_over_boundary():
    # STEP+1 words: second iteration starts at index STEP but only 1 word remains.
    result = chunk_text(_words(STEP + 1))
    assert len(result) == 2


def test_chunk_text_overlap_correctness():
    """The tail of chunk N and the head of chunk N+1 share WORDS_OVERLAP words."""
    # Use WORDS_PER_CHUNK + WORDS_OVERLAP words → exactly 2 chunks with clean overlap.
    n = WORDS_PER_CHUNK + WORDS_OVERLAP  # 432
    result = chunk_text(_words(n))
    assert len(result) == 2
    tail_of_first  = result[0].split()[-WORDS_OVERLAP:]
    head_of_second = result[1].split()[:WORDS_OVERLAP]
    assert tail_of_first == head_of_second


def test_chunk_text_custom_params():
    chunk_size, overlap = 100, 20
    words_per = int(100 * 0.75)   # 75
    words_ov  = int(20  * 0.75)   # 15
    result = chunk_text(_words(words_per + 1), chunk_size=chunk_size, overlap=overlap)
    assert len(result) == 2
    assert len(result[0].split()) == words_per


# ---------------------------------------------------------------------------
# parse_csv
# ---------------------------------------------------------------------------

def _csv_file(content: str, tmp_path):
    p = tmp_path / "test.csv"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_parse_csv_typical_row(tmp_path):
    content = "date,amount,merchant\n2024-03-01,42.50,Whole Foods"
    result = parse_csv(_csv_file(content, tmp_path))
    assert result == "date: 2024-03-01, amount: 42.50, merchant: Whole Foods"


def test_parse_csv_empty_values_filtered(tmp_path):
    content = "date,amount,merchant\n2024-03-01,,Starbucks"
    result = parse_csv(_csv_file(content, tmp_path))
    assert "amount" not in result
    assert "date: 2024-03-01" in result
    assert "merchant: Starbucks" in result


def test_parse_csv_multi_row(tmp_path):
    content = "date,amount\n2024-03-01,10.00\n2024-03-02,20.00\n2024-03-03,30.00"
    result = parse_csv(_csv_file(content, tmp_path))
    lines = result.split("\n")
    assert len(lines) == 3
