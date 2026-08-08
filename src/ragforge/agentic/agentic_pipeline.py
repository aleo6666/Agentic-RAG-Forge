"""Agentic RAG pipeline — Self-RAG style graph.

Flow (all decisions are LLM-driven, all loops bounded):

    route ──direct──→ direct_answer ──→ END
      │
      ├──clarify──→ clarify ──→ END
      │
      └──retrieve──→ grade_docs ──→ generate ──→ grade_answer ──→ END
                          │  ↑                       │  ↑
                    (no relevant)              (not grounded)
                          ▼  │                       ▼  │
                       rewrite ──────────────→ rewrite ─┘
                          │  (bounded by max_rounds)
                          └──→ retrieve

Every external dependency (LLM, retriever, reranker, generator) is injectable
so the graph can be tested end-to-end with fakes — no network, no vector store.
"""

from __future__ import annotations

from typing import Callable

from langgraph.graph import StateGraph, END

from ragforge.pipeline import RetrievedChunk
from ragforge.agentic.agentic_state import AgenticState
from ragforge.agentic.llm import LLMCallFn, default_llm
from ragforge.agentic.query_router import make_route_query
from ragforge.agentic.query_rewriter import make_rewrite_query
from ragforge.agentic.grader import make_grade_documents, make_grade_answer

RetrieverFn = Callable[[str, str, int], list[RetrievedChunk]]
RerankerFn = Callable[[str, list[RetrievedChunk], int], list[RetrievedChunk]]
GeneratorFn = Callable[..., tuple[str, list[dict]]]


def _default_retriever(query: str, tenant_id: str, top_k: int = 20) -> list[RetrievedChunk]:
    from ragforge.retrieval.hybrid import hybrid_retrieve

    return hybrid_retrieve(query, tenant_id=tenant_id, top_k=top_k)


def _default_reranker(query: str, retrieved: list[RetrievedChunk], top_k: int = 5) -> list[RetrievedChunk]:
    from ragforge.retrieval.reranker import rerank_chunks

    return rerank_chunks(query, retrieved, top_k=top_k)


def _default_generator(query: str, context: str, **kwargs) -> tuple[str, list[dict]]:
    from ragforge.generation.generator import generate_answer

    return generate_answer(query, context, **kwargs)


def build_agentic_pipeline(
    llm: LLMCallFn | None = None,
    retriever: RetrieverFn | None = None,
    reranker: RerankerFn | None = None,
    generator: GeneratorFn | None = None,
    max_rounds: int = 3,
):
    """Build the agentic RAG graph. Pass fakes to test without network/vector store."""
    llm = llm or default_llm
    retriever = retriever or _default_retriever
    reranker = reranker or _default_reranker
    generator = generator or _default_generator

    route_query = make_route_query(llm)
    rewrite_query = make_rewrite_query(llm)
    grade_documents = make_grade_documents(llm)
    grade_answer = make_grade_answer(llm)

    # ── Nodes ──────────────────────────────────────────────────

    def retrieve(state: AgenticState) -> AgenticState:
        q = state.get("rewritten_query") or state["query"]
        results = retriever(q, state["tenant_id"], top_k=20)
        reranked = reranker(q, results, top_k=5)
        return {
            **state,
            "retrieved": reranked,
            "retrieval_rounds": state.get("retrieval_rounds", 0) + 1,
            "trace": state.get("trace", [])
            + [{"step": "retrieve", "query": q, "hits": len(reranked)}],
        }

    def generate(state: AgenticState) -> AgenticState:
        relevant = [g for g in state.get("graded", []) if g.get("relevant")]
        chunks = relevant or state.get("graded", []) or state.get("retrieved", [])
        context_parts = [c["chunk"]["content"] for c in chunks]
        context = "\n\n---\n\n".join(context_parts)

        if not context_parts:
            answer, citations = "知识库中没有找到相关信息。", []
        else:
            answer, citations = generator(state["query"], context, citation_check=True)

        return {
            **state,
            "context": context,
            "answer": answer,
            "citations": citations,
            "trace": state.get("trace", [])
            + [{"step": "generate", "query": state["query"], "context_chunks": len(context_parts)}],
        }

    def direct_answer(state: AgenticState) -> AgenticState:
        system = "你是 RAG Forge 助手。用户问题无需检索知识库，直接友好、简洁地回答。"
        text = llm([{"role": "user", "content": state["query"]}], system, temperature=0.3)
        return {
            **state,
            "answer": text,
            "citations": [],
            "context": "",
            "trace": state.get("trace", []) + [{"step": "direct", "query": state["query"]}],
        }

    def clarify(state: AgenticState) -> AgenticState:
        """Clarify without coming back empty — attempt a best-effort answer from a
        first-pass retrieval, prefixed with a clarification request."""
        q = state["query"]
        try:
            results = retriever(q, state["tenant_id"], top_k=20)
            reranked = reranker(q, results, top_k=3)
            if reranked:
                context_parts = [r["chunk"]["content"] for r in reranked]
                context = "\n\n---\n\n".join(context_parts)
                answer, citations = generator(q, context)
                hint = state.get("clarification") or "请补充更多信息"
                answer = f"（你的问题比较模糊，我先基于已有资料尝试回答；如需更精确，请补充说明：{hint}）\n\n{answer}"
                return {
                    **state,
                    "answer": answer,
                    "citations": citations,
                    "context": context,
                    "trace": state.get("trace", [])
                    + [{"step": "clarify", "query": q, "best_effort": True}],
                }
        except Exception:
            pass
        return {
            **state,
            "answer": state.get("clarification") or "请补充更多信息后重新提问。",
            "citations": [],
            "trace": state.get("trace", []) + [{"step": "clarify", "query": q, "best_effort": False}],
        }

    # ── Conditional edges ──────────────────────────────────────

    def route_decider(state: AgenticState) -> str:
        return {"retrieve": "retrieve", "direct": "direct", "clarify": "clarify"}.get(
            state.get("route_decision"), "retrieve"
        )

    def after_grade(state: AgenticState) -> str:
        # Round budget exhausted → generate with whatever we have (graceful degrade)
        if state.get("retrieval_rounds", 0) >= state.get("max_rounds", max_rounds):
            return "generate"
        if state.get("graded") and any(g.get("relevant") for g in state["graded"]):
            return "generate"
        return "rewrite"

    def after_answer_grade(state: AgenticState) -> str:
        if (
            not state.get("answer_grounded", True)
            and state.get("retrieval_rounds", 0) < state.get("max_rounds", max_rounds)
        ):
            return "rewrite"
        return "end"

    # ── Graph ──────────────────────────────────────────────────

    graph = StateGraph(AgenticState)
    graph.add_node("route", route_query)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_docs", grade_documents)
    graph.add_node("rewrite", rewrite_query)
    graph.add_node("generate", generate)
    graph.add_node("grade_answer", grade_answer)
    graph.add_node("direct", direct_answer)
    graph.add_node("clarify", clarify)

    graph.set_entry_point("route")
    graph.add_conditional_edges(
        "route",
        route_decider,
        {"retrieve": "retrieve", "direct": "direct", "clarify": "clarify"},
    )
    graph.add_edge("retrieve", "grade_docs")
    graph.add_conditional_edges(
        "grade_docs",
        after_grade,
        {"generate": "generate", "rewrite": "rewrite"},
    )
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("generate", "grade_answer")
    graph.add_conditional_edges(
        "grade_answer",
        after_answer_grade,
        {"rewrite": "rewrite", "end": END},
    )
    graph.add_edge("direct", END)
    graph.add_edge("clarify", END)

    return graph


def run_agentic_query(
    query: str,
    tenant_id: str = "default",
    max_rounds: int = 3,
    **deps,
) -> AgenticState:
    """Run the agentic query end-to-end. ``deps`` overrides LLM/retriever/reranker/generator."""
    graph = build_agentic_pipeline(max_rounds=max_rounds, **deps).compile()
    return graph.invoke(
        {
            "query": query,
            "tenant_id": tenant_id,
            "retrieval_rounds": 0,
            "max_rounds": max_rounds,
            "trace": [],
            "errors": [],
        }
    )
