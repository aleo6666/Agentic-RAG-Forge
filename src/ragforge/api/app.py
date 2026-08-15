"""RAG Forge FastAPI application."""

import mimetypes
import os

# Windows 下 mimetypes 可能把 .js 注册为 text/plain → 浏览器拒绝执行。
# 显式修正常见前端 MIME。
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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

# 多轮会话：把最近 N 轮（每轮 = 一问一答）历史注入生成 prompt
HISTORY_ROUNDS = 4


# ── Request Models ───────────────────────────────────────────────

class IngestRequest(BaseModel):
    paths: list[str]
    tenant_id: str = "default"
    strategy: str = "paragraph"


class AskRequest(BaseModel):
    question: str
    tenant_id: str = "default"


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    question: str
    tenant_id: str = "default"  # 与 /agent-ask 一致：tenant 以 API key 为准，此字段仅占位


# ── Routes ───────────────────────────────────────────────────────

@app.get("/")
def root():
    """Frontend SPA when built, otherwise interactive API docs."""
    if _DIST.exists():
        return FileResponse(_DIST / "index.html")
    return RedirectResponse(url="/docs")


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


@app.post("/upload")
@rate_limiter(limit=10, window=60)
def api_upload(file: UploadFile = File(...), tenant: str = Depends(require_tenant)):
    """Upload a document file → parse → chunk → embed → index. Requires X-API-Key."""
    import os
    import shutil
    import tempfile

    from ragforge.ingestion.parser import parse_file
    from ragforge.ingestion.chunker import chunk_documents
    from ragforge.indexing.embedder import embed_chunks
    from ragforge.indexing.vector_store import index_chunks
    from ragforge.cache.embedding_cache import EmbeddingCache

    suffix = Path(file.filename or "upload").suffix or ".txt"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        doc = parse_file(Path(tmp.name), tenant_id=tenant)
        doc["metadata"]["filename"] = file.filename or Path(tmp.name).name
        chunks = chunk_documents([doc])
        cache = EmbeddingCache()
        chunks = embed_chunks(chunks, cache=cache, tenant_id=tenant)
        index_chunks(chunks, tenant_id=tenant)
    finally:
        tmp.close()
        os.unlink(tmp.name)

    audit_log("upload", tenant=tenant, detail=file.filename or "?")
    return {
        "status": "ok",
        "filename": file.filename,
        "chars": doc["metadata"].get("char_count", 0),
        "chunks": len(chunks),
    }


@app.get("/documents")
@rate_limiter(limit=30, window=60)
def api_documents(tenant: str = Depends(require_tenant)):
    """List indexed documents (aggregated by doc_id)."""
    from ragforge.indexing.vector_store import list_documents

    docs = list_documents(tenant)
    return {"status": "ok", "tenant": tenant, "documents": docs}


@app.delete("/documents")
@rate_limiter(limit=5, window=60)
def api_clear_documents(tenant: str = Depends(require_tenant)):
    """Clear the tenant's whole knowledge base."""
    from ragforge.indexing.vector_store import clear_documents

    removed = clear_documents(tenant)
    audit_log("clear", tenant=tenant, detail=f"{removed} chunks removed")
    return {"status": "ok", "removed_chunks": removed}


@app.get("/config")
@rate_limiter(limit=30, window=60)
def api_config(tenant: str = Depends(require_tenant)):
    """Runtime config summary (no secrets)."""
    from ragforge.config import get_config

    cfg = get_config()
    return {
        "status": "ok",
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.llm_model,
        "llm_endpoint": cfg.llm_endpoint,
        "embedding_provider": cfg.embedding_provider,
        "embedding_model": cfg.embedding_model,
        "reranker_model": cfg.reranker_model,
        "llm_key_configured": bool(cfg.llm_api_key),
        "embedding_key_configured": bool(cfg.embedding_api_key),
        "api_key_configured": bool(os.getenv("RAGFORGE_API_KEY")),
    }


@app.post("/agent-ask")
@rate_limiter(limit=30, window=60)
def api_agent_ask(req: AskRequest, tenant: str = Depends(require_tenant)):
    """Agentic query — routing, grading, rewrite loops. Requires X-API-Key header."""
    from ragforge.agentic.agentic_pipeline import run_agentic_query

    audit_log("agent_ask", tenant=tenant, detail=req.question)
    state = run_agentic_query(req.question, tenant_id=tenant)

    return {
        "answer": state["answer"],
        "citations": state.get("citations", []),
        "trace": state.get("trace", []),
        "grounded": state.get("answer_grounded"),
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


@app.post("/session")
@rate_limiter(limit=30, window=60)
def api_create_session(tenant: str = Depends(require_tenant)):
    """Create a new conversation session. Requires X-API-Key header."""
    from ragforge.session.session_store import SessionStore

    store = SessionStore()
    session_id = store.create_session(tenant_id=tenant)
    audit_log("session_create", tenant=tenant, detail=session_id)
    return {"session_id": session_id}


@app.post("/chat")
@rate_limiter(limit=30, window=60)
def api_chat(req: ChatRequest, tenant: str = Depends(require_tenant)):
    """Multi-turn agentic chat. Requires X-API-Key header.

    Without ``session_id`` a new session is created. The most recent
    ``HISTORY_ROUNDS`` turns are injected into the generation prompt so the
    answer can reference prior context. Returns the answer plus citations,
    trace, grounding verdict, session id and round count.
    """
    from ragforge.agentic.agentic_pipeline import run_agentic_query
    from ragforge.session.session_store import SessionStore

    store = SessionStore()

    session_id = req.session_id
    if session_id:
        if not store.session_exists(session_id):
            raise HTTPException(404, f"Session not found: {session_id}")
    else:
        session_id = store.create_session(tenant_id=tenant)

    # 最近 N 轮历史（本轮之前），用于注入生成 prompt
    history = store.recent_messages(session_id, limit=HISTORY_ROUNDS * 2)

    # 先落库用户消息，再生成（生成失败也能保留问题）
    store.append_message(session_id, "user", req.question)

    audit_log("chat", tenant=tenant, detail=req.question)
    state = run_agentic_query(req.question, tenant_id=tenant, history=history)

    store.append_message(session_id, "assistant", state.get("answer", ""))

    # 未命中问题自动收集：仅当「确认知识库无答案」时记录 —— 检索路由 +
    # rewrite 循环触顶（retrieval_rounds 用尽）且最终无任何相关文档。
    # 注意：不能用 answer_grounded 判定 —— 系统对"诚实回答无答案"也会判
    # grounded=True（回答完全基于上下文，未编造）。未命中的可靠信号是
    # 「检索用尽 + 无相关文档」。
    graded = state.get("graded") or []
    retrieval_exhausted = (
        state.get("route_decision") == "retrieve"
        and state.get("retrieval_rounds", 0) >= state.get("max_rounds", 3)
        and not any(g.get("relevant") for g in graded)
    )
    if retrieval_exhausted:
        store.record_missed_question(session_id, req.question, tenant_id=tenant)

    return {
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "trace": state.get("trace", []),
        "grounded": state.get("answer_grounded"),
        "session_id": session_id,
        "rounds": store.round_count(session_id),
    }


@app.get("/missed-questions")
@rate_limiter(limit=30, window=60)
def api_missed_questions(status: Optional[str] = None, tenant: str = Depends(require_tenant)):
    """List unanswered questions (operations closed loop). Requires X-API-Key header.

    Tenant-scoped: only this tenant's missed questions are returned, newest
    first. Optional ``?status=new`` filters to unresolved items.
    """
    from ragforge.session.session_store import SessionStore

    store = SessionStore()
    items = store.list_missed_questions(tenant_id=tenant, status=status)
    return {"status": "ok", "tenant": tenant, "missed_questions": items}


# ── Static frontend (built Vue app) ─────────────────────────────
# Mounted only when frontend/dist exists — keeps API-only deploys working.

_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        """Serve built SPA with history-fallback to index.html."""
        file = _DIST / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(_DIST / "index.html")
