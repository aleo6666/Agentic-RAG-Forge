"""Human handoff / ticket management tests (smart customer service ops loop, step 2).

Covers:
  ① POST /tickets → create ticket (status 'open')
  ② same session + same question → deduplicated (idempotent id)
  ③ GET /tickets → tenant isolation (+ ?status= filter)
  ④ PATCH /tickets/{id} → mark resolved
  ⑤ PATCH non-owner tenant → 404

No network, no vector store — endpoint functions are called directly (they are
async via the ``rate_limiter`` wrapper, so ``asyncio.run`` drives them), matching
the pattern in tests/test_missed.py.
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ["DEEPSEEK_API_KEY"] = "sk-test"

import pytest

from ragforge.session.session_store import SessionStore


def _patch_db(monkeypatch, tmp_path):
    """Point SessionStore at a temp DB and return its path."""
    db = tmp_path / "sessions.db"
    monkeypatch.setenv("RAGFORGE_SESSION_DB", str(db))
    return db


# ── ① 创建工单 ─────────────────────────────────────────────────

def test_create_ticket(monkeypatch, tmp_path):
    from ragforge.api.app import api_create_ticket, TicketCreateRequest

    db = _patch_db(monkeypatch, tmp_path)
    store = SessionStore(db_path=db)
    sid = store.create_session(tenant_id="t1")

    result = asyncio.run(
        api_create_ticket(
            TicketCreateRequest(
                session_id=sid, question="转人工：退款", contact="13800000000"
            ),
            tenant="t1",
        )
    )
    assert result["ticket_id"]

    tickets = store.list_tickets(tenant_id="t1")
    assert len(tickets) == 1
    assert tickets[0]["session_id"] == sid
    assert tickets[0]["question"] == "转人工：退款"
    assert tickets[0]["contact"] == "13800000000"
    assert tickets[0]["status"] == "open"


# ── ② 同 session 同问题去重 ────────────────────────────────────

def test_duplicate_ticket_idempotent(monkeypatch, tmp_path):
    from ragforge.api.app import api_create_ticket, TicketCreateRequest

    db = _patch_db(monkeypatch, tmp_path)
    store = SessionStore(db_path=db)
    sid = store.create_session(tenant_id="t1")

    r1 = asyncio.run(
        api_create_ticket(
            TicketCreateRequest(session_id=sid, question="重复问题"), tenant="t1"
        )
    )
    r2 = asyncio.run(
        api_create_ticket(
            TicketCreateRequest(session_id=sid, question="重复问题"), tenant="t1"
        )
    )
    assert r1["ticket_id"] == r2["ticket_id"]
    assert len(store.list_tickets(tenant_id="t1")) == 1


# ── ③ GET 租户隔离 + status 过滤 ───────────────────────────────

def test_list_tickets_tenant_isolation(monkeypatch, tmp_path):
    from ragforge.api.app import api_list_tickets

    db = _patch_db(monkeypatch, tmp_path)
    store = SessionStore(db_path=db)
    sa = store.create_session(tenant_id="tenant-a")
    sb = store.create_session(tenant_id="tenant-b")
    store.create_ticket(sa, "A 的工单", tenant_id="tenant-a")
    store.create_ticket(sb, "B 的工单", tenant_id="tenant-b")

    result = asyncio.run(api_list_tickets(tenant="tenant-a"))
    assert result["tenant"] == "tenant-a"
    assert [t["question"] for t in result["tickets"]] == ["A 的工单"]


def test_list_tickets_status_filter(monkeypatch, tmp_path):
    from ragforge.api.app import api_list_tickets

    db = _patch_db(monkeypatch, tmp_path)
    store = SessionStore(db_path=db)
    sid = store.create_session(tenant_id="t1")
    t_open = store.create_ticket(sid, "待处理", tenant_id="t1")
    t_resolved = store.create_ticket(sid, "已解决", tenant_id="t1")
    store.resolve_ticket(t_resolved, tenant_id="t1")

    open_items = asyncio.run(api_list_tickets(status="open", tenant="t1"))
    assert [t["question"] for t in open_items["tickets"]] == ["待处理"]

    all_items = asyncio.run(api_list_tickets(tenant="t1"))
    assert {t["question"] for t in all_items["tickets"]} == {"待处理", "已解决"}


# ── ④ PATCH 标记 resolved ─────────────────────────────────────

def test_resolve_ticket(monkeypatch, tmp_path):
    from ragforge.api.app import api_resolve_ticket, TicketUpdateRequest

    db = _patch_db(monkeypatch, tmp_path)
    store = SessionStore(db_path=db)
    sid = store.create_session(tenant_id="t1")
    tid = store.create_ticket(sid, "需人工处理", tenant_id="t1")

    result = asyncio.run(
        api_resolve_ticket(tid, TicketUpdateRequest(status="resolved"), tenant="t1")
    )
    assert result["ticket_id"] == tid
    assert result["ticket_status"] == "resolved"

    tickets = store.list_tickets(tenant_id="t1")
    assert tickets[0]["status"] == "resolved"


# ── ⑤ PATCH 非本租户 404 ──────────────────────────────────────

def test_resolve_ticket_foreign_tenant_404(monkeypatch, tmp_path):
    from ragforge.api.app import api_resolve_ticket, TicketUpdateRequest
    from fastapi import HTTPException

    db = _patch_db(monkeypatch, tmp_path)
    store = SessionStore(db_path=db)
    sid = store.create_session(tenant_id="tenant-a")
    tid = store.create_ticket(sid, "A 的工单", tenant_id="tenant-a")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api_resolve_ticket(
                tid, TicketUpdateRequest(status="resolved"), tenant="tenant-b"
            )
        )
    assert exc.value.status_code == 404

    # 未被误改
    assert store.list_tickets(tenant_id="tenant-a")[0]["status"] == "open"
