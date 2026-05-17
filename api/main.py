import json
import os
import tempfile

from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

import anthropic
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel
from supabase import Client, create_client

from pipeline.embed import embed_chunks, embed_query
from pipeline.ingest import chunk_text, parse_csv, parse_pdf
from pipeline.store import similarity_search, upsert_chunks, upsert_document

app = FastAPI(title="FinSight API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_supabase: Client | None = None
_anthropic: anthropic.Anthropic | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _supabase


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _anthropic


@app.post("/upload")
async def upload(file: UploadFile):
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    if suffix not in (".pdf", ".csv"):
        raise HTTPException(status_code=422, detail=f"Unsupported file type '{suffix}'. Only .pdf and .csv are accepted.")

    contents = await file.read()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(contents)
        tmp.flush()
        tmp.close()

        if suffix == ".pdf":
            text = parse_pdf(tmp.name)
        else:
            text = parse_csv(tmp.name)
    finally:
        os.unlink(tmp.name)

    chunks = chunk_text(text)
    embeddings = embed_chunks(chunks)

    stem = file.filename.rsplit(".", 1)[0] if file.filename and "." in file.filename else file.filename or "untitled"
    doc_id = upsert_document(
        title=stem,
        source=file.filename or "untitled",
        content=text,
        metadata={"file_name": file.filename, "file_size": len(contents)},
    )
    upsert_chunks(doc_id, chunks, embeddings)

    return {"document_id": doc_id, "chunk_count": len(chunks)}


@app.get("/documents")
def documents():
    result = (
        _get_supabase()
        .table("documents")
        .select("id,title,source,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return {"documents": result.data}


class QueryRequest(BaseModel):
    question: str


@app.post("/query")
def query(body: QueryRequest):
    vector = embed_query(body.question)
    chunks = similarity_search(vector, top_k=5)

    if not chunks:
        return {"answer": "No relevant documents found. Please upload a document first.", "sources": []}

    context = "\n---\n".join(c["content"] for c in chunks)
    prompt = (
        "You are a financial assistant. Answer the question using only the provided context. "
        "Be concise and specific. If the answer is not in the context, say so.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {body.question}"
    )

    response = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    answer = response.content[0].text
    sources = [c["content"][:200] for c in chunks]

    return {"answer": answer, "sources": sources}


@app.get("/stats")
def stats():
    result = (
        _get_supabase()
        .table("documents")
        .select("content")
        .execute()
    )
    docs = result.data
    if not docs:
        return {"total_spending": 0.0, "total_income": 0.0, "largest_transaction": 0.0}

    combined = ""
    for doc in docs:
        excerpt = (doc.get("content") or "")[:3000]
        combined = (combined + "\n---\n" + excerpt)[:8000]

    prompt = (
        "You are a financial data extractor. From the documents below, compute:\n"
        "- total_spending: sum of all outgoing payments, expenses, and debits (positive number)\n"
        "- total_income: sum of all incoming payments, deposits, and credits (positive number)\n"
        "- largest_transaction: the single largest individual transaction amount (positive number)\n\n"
        "Respond with ONLY a JSON object in this exact format, no extra text:\n"
        '{"total_spending": <number>, "total_income": <number>, "largest_transaction": <number>}\n\n'
        f"Documents:\n{combined}"
    )

    response = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        data = json.loads(response.content[0].text.strip())
        return {
            "total_spending": float(data.get("total_spending", 0)),
            "total_income": float(data.get("total_income", 0)),
            "largest_transaction": float(data.get("largest_transaction", 0)),
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"total_spending": 0.0, "total_income": 0.0, "largest_transaction": 0.0}


handler = Mangum(app)
