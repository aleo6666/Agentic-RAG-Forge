"""Session / multi-turn chat tests.

Covers:
  ① session creation
  ② auto-create when no session_id
  ③ multi-turn context injection (fake LLM — history really reaches the
     generation prompt)
  ④ history persistence (reopen the store and still read it back)

No network, no vector store — every heavy dependency is faked, matching the
pattern in tests/test_agentic.py.
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ["DEEPSEEK_API_KEY"] = "sk-test"

import pytest

from ragforge.session.session_store import SessionStore


# ── ① Session store ─────────────────────────────────────────────

def test_create_session(tmp_path):
    store = SessionStore(db_path=tmp_path / "sessions.db")
    sid = store.create_session(tenant_id="t1")
    assert sid
    assert store.session_exists(sid)
    assert not store.session_exists("nonexistent")


def test_append_and_recent_messages(tmp_path):
    store = SessionStore(db_path=tmp_path / "sessions.db")
    sid = store.create_session()
    store.append_message(sid, "user", "什么是RAG？")
    store.append_message(sid, "assistant", "RAG是检索增强生成。")
    store.append_message(sid, "user", "它有什么优点？")

    msgs = store.recent_messages(sid, limit=4)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "什么是RAG？"
    # limit 截断到最近 N 条（时间顺序）
    assert [m["content"] for m in store.recent_messages(sid, limit=2)] == [
        "RAG是检索增强生成。",
        "它有什么优点？",
    ]


def test_invalid_role_rejected(tmp_path):
    store = SessionStore(db_path=tmp_path / "sessions.db")
    sid = store.create_session()
    with pytest.raises(ValueError):
        store.append_message(sid, "system", "不应被接受")


def test_round_count(tmp_path):
    store = SessionStore(db_path=tmp_path / "sessions.db")
    sid = store.create_session()
    assert store.round_count(sid) == 0
    store.append_message(sid, "user", "Q1")
    store.append_message(sid, "assistant", "A1")
    store.append_message(sid, "user", "Q2")
    assert store.round_count(sid) == 2


def test_list_sessions_tenant_scoped(tmp_path):
    store = SessionStore(db_path=tmp_path / "sessions.db")
    a = store.create_session(tenant_id="tenant-a")
    b = store.create_session(tenant_id="tenant-b")
    assert {s["id"] for s in store.list_sessions("tenant-a")} == {a}
    assert {s["id"] for s in store.list_sessions()} == {a, b}


def test_history_persists_across_store_instances(tmp_path):
    """④ 重建存储对象仍能读到历史。"""
    db = tmp_path / "sessions.db"
    store = SessionStore(db_path=db)
    sid = store.create_session()
    store.append_message(sid, "user", "第一个问题")
    store.append_message(sid, "assistant", "第一个答案")

    reopened = SessionStore(db_path=db)  # 全新对象，同一文件
    msgs = reopened.recent_messages(sid)
    assert [m["content"] for m in msgs] == ["第一个问题", "第一个答案"]


# ── ③ History injection ─────────────────────────────────────────

def test_history_reaches_generation_prompt(monkeypatch):
    """fake LLM：历史确实拼进 generate_answer 的 user prompt。"""
    import httpx

    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs.get("json")

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "基于上下文的答案。"}}]}

        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)

    from ragforge.generation.generator import generate_answer

    history = [
        {"role": "user", "content": "什么是RAG？"},
        {"role": "assistant", "content": "RAG是检索增强生成。"},
    ]
    generate_answer("它有什么优点？", "优点包括降低幻觉。", history=history, citation_check=False)

    user_prompt = captured["json"]["messages"][1]["content"]
    assert "什么是RAG？" in user_prompt
    assert "RAG是检索增强生成" in user_prompt
    assert "它有什么优点？" in user_prompt  # 当前问题仍在

    # 无历史时不注入
    generate_answer("独立问题", "上下文", citation_check=False)
    assert "对话历史" not in captured["json"]["messages"][1]["content"]


def test_run_agentic_query_injects_history():
    """端到端：run_agentic_query 把 history 传给生成器（图结构不动）。"""
    from ragforge.agentic.agentic_pipeline import run_agentic_query

    captured = {}

    class FakeLLM:
        def __init__(self, responses):
            self._responses = list(responses)

        def __call__(self, messages, system, temperature=0.0):
            return self._responses.pop(0) if self._responses else '{"action": "direct"}'

    def retriever(query, tenant_id, top_k=20):
        return [
            {
                "chunk": {"id": "c1", "content": "优点：降低幻觉", "doc_id": "d1", "metadata": {}},
                "score": 0.9,
                "source": "hybrid",
            }
        ]

    def reranker(query, retrieved, top_k=5):
        return retrieved[:top_k]

    def generator(query, context, **kwargs):
        captured["query"] = query
        captured["history"] = kwargs.get("history")
        return "基于上下文的答案。", [{"source": "chunk_0", "snippet": context[:60]}]

    history = [
        {"role": "user", "content": "什么是RAG？"},
        {"role": "assistant", "content": "RAG是检索增强生成。"},
    ]

    state = run_agentic_query(
        "它有什么优点？",
        tenant_id="test",
        history=history,
        llm=FakeLLM([
            '{"query": "RAG 有什么优点？", "reason": "补全指代"}',  # contextualize
            '{"action": "retrieve", "reason": "需要知识库"}',
            '{"relevant": [0], "irrelevant": [], "reason": "相关"}',
            '{"grounded": true, "reason": "有依据"}',
        ]),
        retriever=retriever,
        reranker=reranker,
        generator=generator,
    )

    assert captured["query"] == "RAG 有什么优点？"  # contextualized
    assert captured["history"] == history
    assert state["answer"] == "基于上下文的答案。"
    assert state["original_query"] == "它有什么优点？"
    assert state["contextualized_query"] == "RAG 有什么优点？"


# ── ② API 端点逻辑（直接调用端点函数，零网络零向量库）──────────

def _patch_chat(monkeypatch, tmp_path):
    monkeypatch.setenv("RAGFORGE_SESSION_DB", str(tmp_path / "sessions.db"))
    captured = []

    def fake_run(query, tenant_id="default", history=None, **deps):
        captured.append({"query": query, "tenant_id": tenant_id, "history": history})
        return {
            "answer": "假答案",
            "citations": [],
            "trace": [{"step": "generate"}],
            "answer_grounded": True,
        }

    monkeypatch.setattr("ragforge.agentic.agentic_pipeline.run_agentic_query", fake_run)
    return captured


def test_chat_auto_creates_session(monkeypatch, tmp_path):
    """② 无 session_id 自动建。"""
    from ragforge.api.app import api_chat, ChatRequest

    captured = _patch_chat(monkeypatch, tmp_path)
    result = asyncio.run(api_chat(ChatRequest(question="你好"), tenant="test-tenant"))

    assert result["session_id"]
    assert result["rounds"] == 1
    assert result["answer"] == "假答案"
    assert captured[0]["query"] == "你好"
    assert captured[0]["history"] == []  # 首轮无历史


def test_chat_multi_turn_references_history(monkeypatch, tmp_path):
    """③ 多轮引用上文：第二轮生成时历史注入第一轮的一问一答。"""
    from ragforge.api.app import api_chat, ChatRequest

    captured = _patch_chat(monkeypatch, tmp_path)
    r1 = asyncio.run(api_chat(ChatRequest(question="什么是RAG？"), tenant="test-tenant"))
    sid = r1["session_id"]

    r2 = asyncio.run(
        api_chat(ChatRequest(session_id=sid, question="它有什么优点？"), tenant="test-tenant")
    )
    assert r2["session_id"] == sid
    assert r2["rounds"] == 2

    hist = captured[1]["history"]
    assert [(m["role"], m["content"]) for m in hist] == [
        ("user", "什么是RAG？"),
        ("assistant", "假答案"),
    ]


def test_create_session_endpoint(monkeypatch, tmp_path):
    from ragforge.api.app import api_create_session

    monkeypatch.setenv("RAGFORGE_SESSION_DB", str(tmp_path / "sessions.db"))
    result = asyncio.run(api_create_session(tenant="test-tenant"))
    assert result["session_id"]
