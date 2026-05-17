import io
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

FAKE_DOC_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_CHUNKS = ["chunk one", "chunk two"]
FAKE_EMBEDDINGS = [[0.1] * 1024, [0.2] * 1024]


def _upload(filename: str, content: bytes = b"fake content"):
    return client.post(
        "/upload",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
    )


# ---------------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------------

def test_upload_rejects_unsupported_type():
    resp = _upload("report.txt")
    assert resp.status_code == 422
    assert "Unsupported" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def _patch_pipeline(mocker):
    mocker.patch("api.main.parse_pdf", return_value="sample text")
    mocker.patch("api.main.parse_csv", return_value="sample text")
    mocker.patch("api.main.chunk_text", return_value=FAKE_CHUNKS)
    mocker.patch("api.main.embed_chunks", return_value=FAKE_EMBEDDINGS)
    mocker.patch("api.main.upsert_document", return_value=FAKE_DOC_ID)
    mocker.patch("api.main.upsert_chunks", return_value=None)


def test_upload_pdf_accepted(mocker):
    _patch_pipeline(mocker)
    resp = _upload("statement.pdf", b"%PDF-fake")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == FAKE_DOC_ID
    assert body["chunk_count"] == len(FAKE_CHUNKS)


def test_upload_csv_accepted(mocker):
    _patch_pipeline(mocker)
    resp = _upload("expenses.csv", b"date,amount\n2024-03-01,42.50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == FAKE_DOC_ID
    assert body["chunk_count"] == len(FAKE_CHUNKS)


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------

def _mock_supabase_docs(mocker, docs: list[dict]):
    sb = MagicMock()
    sb.table.return_value.select.return_value.execute.return_value.data = docs
    mocker.patch("api.main._get_supabase", return_value=sb)
    return sb


def _mock_anthropic_stats(mocker, text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    client_mock = MagicMock()
    client_mock.messages.create.return_value = msg
    mocker.patch("api.main._get_anthropic", return_value=client_mock)


def test_stats_no_documents(mocker):
    _mock_supabase_docs(mocker, [])
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"total_spending": 0.0, "total_income": 0.0, "largest_transaction": 0.0}


def test_stats_with_documents(mocker):
    _mock_supabase_docs(mocker, [{"content": "Income: $3450. Spending: $248.21. Largest: $200."}])
    _mock_anthropic_stats(mocker, '{"total_spending": 248.21, "total_income": 3450.0, "largest_transaction": 200.0}')
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_spending"] == pytest.approx(248.21)
    assert body["total_income"] == pytest.approx(3450.0)
    assert body["largest_transaction"] == pytest.approx(200.0)


def test_stats_bad_llm_response(mocker):
    _mock_supabase_docs(mocker, [{"content": "some financial text"}])
    _mock_anthropic_stats(mocker, "I cannot determine the exact figures.")
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"total_spending": 0.0, "total_income": 0.0, "largest_transaction": 0.0}


def test_stats_markdown_fenced_response(mocker):
    _mock_supabase_docs(mocker, [{"content": "Income: $3450. Spending: $248.21. Largest: $200."}])
    _mock_anthropic_stats(mocker, '```json\n{"total_spending": 248.21, "total_income": 3450.0, "largest_transaction": 200.0}\n```')
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_spending"] == pytest.approx(248.21)
    assert body["total_income"] == pytest.approx(3450.0)
    assert body["largest_transaction"] == pytest.approx(200.0)
