import pytest


def make_words(n: int) -> str:
    """Return a string of n distinct words for chunk_text testing."""
    return " ".join(f"word{i}" for i in range(n))


@pytest.fixture
def words():
    return make_words


SAMPLE_CSV = "date,amount,merchant\n2024-03-01,42.50,Whole Foods\n2024-03-05,12.00,Starbucks\n2024-03-10,95.00,Amazon"
