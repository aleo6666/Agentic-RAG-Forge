"""Missed-question auto-collection tests (smart customer service ops loop, step 1).

Covers:
  ① grounded=False + rewrite loop exhausted → recorded
  ② grounded=True → not recorded
  ③ grounded=None / direct chit-chat → not recorded
  ④ same session + same question → deduplicated
  ⑤ GET /missed-questions → tenant isolation (+ status filter)

No network, no vector store — ``run_agentic_query`` is monkeypatched to return a
constructed ``AgenticState``, matching the ``_patch_chat`` pattern in
tests/test_sessions.py.
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ["DEEPSEEK_API_KEY"] = "sk-test"

from ragforge.session.session_store import SessionStore


# ── helpers ─────────────────────────────────────────────────────

def _make_state(**overrides):
    """A grounded retrieve answer by default; override fields to simulate other outcomes."""
    state = {
        "answer": "知识库中找到的答案。",
        "citations": [],
        "trace": [{"step": "generate"}],
        "answer_grounded": True,
        "route_decision": "retrieve",
        "retrieval_rounds": 1,
        "max_rounds": 3,
        "graded": [{"relevant": True, "chunk": {"id": "c1"}}],
    }
    state.update(overrides)
    return state


def _patch_chat(monkeypatch, tmp_path, state=None):
    """Point api_chat's SessionStore at a temp DB and stub run_agentic_query."""
    monkeypatch.setenv("RAGFORGE_SESSION_DB", str(tmp_path / "sessions.db"))
    captured = []

    def fake_run(query, tenant_id="default", history=None, **deps):
        captured.append({"query": query, "tenant_id": tenant_id, "history": history})
        return state if state is not None else _make_state()

    monkeypatch.setattr("ragforge.agentic.agentic_pipeline.run_agentic_query", fake_run)
    return captured


# ── ① 检索用尽 + 无相关文档 → 入库 ─────────────────────────────

def test_missed_collected_when_rounds_exhausted_and_no_relevant(monkeypatch, tmp_path):
    from ragforge.api.app import api_chat, ChatRequest

    _patch_chat(
        monkeypatch,
        tmp_path,
        state=_make_state(
            answer_grounded=False,
            retrieval_rounds=3,
            max_rounds=3,
            graded=[{"relevant": False, "chunk": {"id": "cX"}}],
        ),
    )
    result = asyncio.run(
        api_chat(ChatRequest(question="这个产品支持退款吗？"), tenant="t1")
    )
    sid = result["session_id"]

    store = SessionStore(db_path=tmp_path / "sessions.db")
    items = store.list_missed_questions(tenant_id="t1")
    assert len(items) == 1
    assert items[0]["question"] == "这个产品支持退款吗？"
    assert items[0]["session_id"] == sid
    assert items[0]["status"] == "new"


# ── ② grounded=True → 不入库 ────────────────────────────────────

def test_grounded_true_not_collected(monkeypatch, tmp_path):
    from ragforge.api.app import api_chat, ChatRequest

    _patch_chat(
        monkeypatch,
        tmp_path,
        state=_make_state(answer_grounded=True, retrieval_rounds=3, max_rounds=3),
    )
    asyncio.run(api_chat(ChatRequest(question="正常问题"), tenant="t1"))

    store = SessionStore(db_path=tmp_path / "sessions.db")
    assert store.list_missed_questions(tenant_id="t1") == []


def test_grounded_none_not_collected(monkeypatch, tmp_path):
    """grounded 为 None（未判定）但有相关文档 → 不收集（新判定看检索结果，不看 grounded）。"""
    from ragforge.api.app import api_chat, ChatRequest

    _patch_chat(
        monkeypatch,
        tmp_path,
        state=_make_state(answer_grounded=None, retrieval_rounds=3, max_rounds=3),
    )
    asyncio.run(api_chat(ChatRequest(question="问题"), tenant="t1"))

    store = SessionStore(db_path=tmp_path / "sessions.db")
    assert store.list_missed_questions(tenant_id="t1") == []


# ── ③ direct 闲聊 → 不入库 ─────────────────────────────────────

def test_direct_chitchat_not_collected(monkeypatch, tmp_path):
    """direct 路由不产生 grounding 判定（无 answer_grounded 字段）→ 不收集。"""
    from ragforge.api.app import api_chat, ChatRequest

    state = {
        "answer": "你好！我是 RAG 助手。",
        "citations": [],
        "trace": [{"step": "direct"}],
        # 无 answer_grounded / retrieval_rounds —— 与 direct_answer 节点输出一致
    }
    _patch_chat(monkeypatch, tmp_path, state=state)
    asyncio.run(api_chat(ChatRequest(question="你好"), tenant="t1"))

    store = SessionStore(db_path=tmp_path / "sessions.db")
    assert store.list_missed_questions(tenant_id="t1") == []


# ── ④ 同 session 同问题去重 ────────────────────────────────────

def test_duplicate_missed_not_recollected(monkeypatch, tmp_path):
    from ragforge.api.app import api_chat, ChatRequest

    _patch_chat(
        monkeypatch,
        tmp_path,
        state=_make_state(
            answer_grounded=False,
            retrieval_rounds=3,
            max_rounds=3,
            graded=[],
        ),
    )
    r1 = asyncio.run(api_chat(ChatRequest(question="退款政策？"), tenant="t1"))
    sid = r1["session_id"]
    r2 = asyncio.run(
        api_chat(ChatRequest(session_id=sid, question="退款政策？"), tenant="t1")
    )
    assert r2["session_id"] == sid

    store = SessionStore(db_path=tmp_path / "sessions.db")
    assert len(store.list_missed_questions(tenant_id="t1")) == 1


def test_record_missed_returns_false_on_duplicate(tmp_path):
    """store 层：第二次记录同 session 同问题返回 False。"""
    store = SessionStore(db_path=tmp_path / "sessions.db")
    sid = store.create_session(tenant_id="t1")
    assert store.record_missed_question(sid, "X", tenant_id="t1") is True
    assert store.record_missed_question(sid, "X", tenant_id="t1") is False


# ── ⑤ GET 端点租户隔离 ─────────────────────────────────────────

def test_missed_questions_endpoint_tenant_isolation(monkeypatch, tmp_path):
    from ragforge.api.app import api_missed_questions

    db = tmp_path / "sessions.db"
    monkeypatch.setenv("RAGFORGE_SESSION_DB", str(db))

    store = SessionStore(db_path=db)
    sa = store.create_session(tenant_id="tenant-a")
    sb = store.create_session(tenant_id="tenant-b")
    store.record_missed_question(sa, "A 的问题", tenant_id="tenant-a")
    store.record_missed_question(sb, "B 的问题", tenant_id="tenant-b")

    result = asyncio.run(api_missed_questions(tenant="tenant-a"))
    assert result["tenant"] == "tenant-a"
    assert [m["question"] for m in result["missed_questions"]] == ["A 的问题"]


def test_missed_questions_status_filter(monkeypatch, tmp_path):
    from ragforge.api.app import api_missed_questions

    db = tmp_path / "sessions.db"
    monkeypatch.setenv("RAGFORGE_SESSION_DB", str(db))

    store = SessionStore(db_path=db)
    sid = store.create_session(tenant_id="t1")
    store.record_missed_question(sid, "未解决", tenant_id="t1")  # status = 'new'

    with store._db() as conn:
        conn.execute(
            "UPDATE missed_questions SET status = 'resolved' WHERE question = '未解决'"
        )
    store.record_missed_question(sid, "另一个未解决", tenant_id="t1")

    new_items = asyncio.run(api_missed_questions(status="new", tenant="t1"))
    assert [m["question"] for m in new_items["missed_questions"]] == ["另一个未解决"]

    all_items = asyncio.run(api_missed_questions(tenant="t1"))
    assert {m["question"] for m in all_items["missed_questions"]} == {
        "未解决",
        "另一个未解决",
    }
