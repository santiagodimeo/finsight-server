import pytest
from unittest.mock import MagicMock, call, patch

from voyageai.error import RateLimitError

import pipeline.embed as embed_module
from pipeline.embed import embed_chunks, embed_query

EMBED_DIM = 1024
BATCH_SIZE = 128  # voyageai.VOYAGE_EMBED_BATCH_SIZE


def _fake_embed_result(texts):
    mock = MagicMock()
    mock.embeddings = [[0.1] * EMBED_DIM for _ in texts]
    return mock


def _make_client(side_effect=None):
    client = MagicMock()
    if side_effect:
        client.embed.side_effect = side_effect
    else:
        client.embed.side_effect = lambda texts, model, input_type: _fake_embed_result(texts)
    return client


# ---------------------------------------------------------------------------
# embed_chunks
# ---------------------------------------------------------------------------

def test_embed_chunks_single_batch(mocker):
    client = _make_client()
    mocker.patch.object(embed_module, "_get_client", return_value=client)
    mocker.patch.object(embed_module, "_client", None)

    chunks = [f"chunk {i}" for i in range(5)]
    result = embed_chunks(chunks)

    assert client.embed.call_count == 1
    _, kwargs = client.embed.call_args
    assert kwargs["input_type"] == "document"
    assert len(result) == 5
    assert all(len(v) == EMBED_DIM for v in result)


def test_embed_chunks_batch_boundary(mocker):
    client = _make_client()
    mocker.patch.object(embed_module, "_get_client", return_value=client)
    mocker.patch.object(embed_module, "_client", None)

    chunks = [f"chunk {i}" for i in range(BATCH_SIZE + 1)]
    result = embed_chunks(chunks)

    assert client.embed.call_count == 2
    first_call_texts = client.embed.call_args_list[0][0][0]
    second_call_texts = client.embed.call_args_list[1][0][0]
    assert len(first_call_texts) == BATCH_SIZE
    assert len(second_call_texts) == 1
    assert len(result) == BATCH_SIZE + 1


def test_embed_chunks_rate_limit_retry(mocker):
    fake_result = _fake_embed_result(["chunk"])
    client = MagicMock()
    client.embed.side_effect = [RateLimitError("rate limited"), fake_result]

    mocker.patch.object(embed_module, "_get_client", return_value=client)
    mocker.patch.object(embed_module, "_client", None)
    mock_sleep = mocker.patch("pipeline.embed.time.sleep")

    result = embed_chunks(["chunk"])

    assert client.embed.call_count == 2
    mock_sleep.assert_called_once()
    assert len(result) == 1


# ---------------------------------------------------------------------------
# embed_query
# ---------------------------------------------------------------------------

def test_embed_query_uses_query_input_type(mocker):
    client = _make_client()
    mocker.patch.object(embed_module, "_get_client", return_value=client)
    mocker.patch.object(embed_module, "_client", None)

    result = embed_query("what is my total spending?")

    assert client.embed.call_count == 1
    _, kwargs = client.embed.call_args
    assert kwargs["input_type"] == "query"
    assert len(result) == EMBED_DIM
