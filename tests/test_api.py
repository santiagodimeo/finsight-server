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
