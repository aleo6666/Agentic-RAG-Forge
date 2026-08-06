"""RAG Forge FastAPI application."""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from ragforge.pipeline import run_indexing, run_query, Document
from ragforge.ingestion.parser import parse_file
from ragforge.enterprise.auth import verify_api_key, require_tenant
from ragforge.enterprise.audit import audit_log
from ragforge.enterprise.rate_limit import rate_limiter

app = FastAPI(title="RAG Forge", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Request Models ───────────────────────────────────────────────

class IngestRequest(BaseModel):
    paths: list[str]
    tenant_id: str = "default"
    strategy: str = "paragraph"


class AskRequest(BaseModel):
    question: str
    tenant_id: str = "default"


# ── Routes ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/ingest")
@rate_limiter(limit=10, window=60)
def api_ingest(req: IngestRequest, tenant: str = Depends(require_tenant)):
    """Ingest documents. Requires X-API-Key header. Tenant from API key, not request body."""
    from ragforge.pipeline import run_indexing, Document

    audit_log("ingest", tenant=tenant, detail=f"{len(req.paths)} files")

    documents = []
    for p in req.paths:
        try:
            doc = parse_file(Path(p), tenant_id=tenant)
            documents.append(doc)
        except Exception as e:
            raise HTTPException(400, f"Failed to parse {p}: {e}")

    state = run_indexing(documents, tenant_id=tenant)
    return {
        "status": "ok",
        "chunks": len(state["chunks"]),
        "documents": len(documents),
    }


@app.post("/ask")
@rate_limiter(limit=30, window=60)
def api_ask(req: AskRequest, tenant: str = Depends(require_tenant)):
    """Query the knowledge base. Requires X-API-Key header. Tenant from API key."""
    audit_log("ask", tenant=tenant, detail=req.question)

    state = run_query(req.question, tenant_id=tenant)
    if state.get("errors"):
        raise HTTPException(500, str(state["errors"]))

    return {
        "answer": state["answer"],
        "citations": state.get("citations", []),
        "evaluation": state.get("evaluation", {}),
    }
