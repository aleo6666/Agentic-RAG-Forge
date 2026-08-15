"""Query contextualization — turns a terse follow-up into a self-contained query.

Multi-turn chat: a follow-up like "它有什么优点？" only makes sense with the
prior turns ("什么是RAG？" → "RAG是检索增强生成..."). The router, rewriter and
retriever all consume ``state["query"]``, so we resolve coreferences ONCE at the
entry point of ``run_agentic_query`` — the graph structure stays untouched and
every downstream node benefits.

Cost: one extra LLM call per turn *only when history exists* (multi-turn).
"""

from __future__ import annotations

from ragforge.agentic.llm import LLMCallFn, llm_json

CONTEXTUALIZE_SYSTEM = """你是对话上下文压缩专家。用户在多轮对话中提出了新问题，请结合对话历史，把问题改写为【不依赖历史也能独立理解】的自包含查询。
要求：
- 补全指代（它/这个/那个/上一条/刚才说/之前提到的等），展开缩略表达
- 保留原始意图；不要回答；不要添加历史中不存在的信息
- 与原始问题同语言
只输出 JSON，格式：{"query": "自包含查询", "reason": "一句话改写理由"}"""


def make_contextualize_query(llm: LLMCallFn):
    """Return a function that rewrites (query, history) → self-contained query."""

    def contextualize_query(query: str, history: list[dict]) -> str:
        if not history:
            return query
        turns = "\n".join(
            f"用户：{m.get('content', '')}" if m.get("role") == "user" else f"助手：{m.get('content', '')}"
            for m in history
        )
        try:
            result = llm_json(
                llm,
                CONTEXTUALIZE_SYSTEM,
                [{"role": "user", "content": f"对话历史：\n{turns}\n\n当前问题：{query}"}],
            )
            new_q = (result.get("query") or "").strip()
            return new_q if new_q and new_q != query else query
        except Exception:
            # Contextualization is an optimization — never break the query on failure.
            return query

    return contextualize_query
