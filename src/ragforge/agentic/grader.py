"""Grading nodes — document relevance filtering + answer groundedness check.

This is the "self-reflection" half of Self-RAG:
  1. grade_documents: drop chunks the LLM judges irrelevant to the query
  2. grade_answer:    check the generated answer is grounded in the context
"""

from ragforge.agentic.llm import LLMCallFn, llm_json
from ragforge.agentic.agentic_state import AgenticState, GradedChunk

GRADE_DOCS_SYSTEM = """你是检索质量评审。判断给定文档是否与用户问题相关。
文档按编号列出，只输出 JSON，格式：
{"relevant": [相关文档的编号数组], "irrelevant": [不相关文档的编号数组], "reason": "一句话总体说明"}"""

GRADE_ANSWER_SYSTEM = """你是答案质检员。判断生成的答案是否完全基于给定上下文，没有编造或脱离上下文的内容。
只输出 JSON，格式：{"grounded": true 或 false, "reason": "一句话理由"}"""


def _as_int_list(raw) -> list[int]:
    """LLM 可能返回字符串编号，统一转 int 并容错。"""
    out = []
    for item in raw or []:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def make_grade_documents(llm: LLMCallFn, top_k: int = 5):
    def grade_documents(state: AgenticState) -> AgenticState:
        results = state.get("retrieved", [])[:top_k]
        q = state.get("rewritten_query") or state["query"]

        if not results:
            return {
                **state,
                "graded": [],
                "last_grade_feedback": "检索结果为空",
                "trace": state.get("trace", [])
                + [{"step": "grade_docs", "query": q, "relevant": 0, "total": 0}],
            }

        doc_list = "\n\n".join(
            f"[{i}] {r['chunk']['content'][:2000]}" for i, r in enumerate(results)
        )
        result = llm_json(
            llm,
            GRADE_DOCS_SYSTEM,
            [{"role": "user", "content": f"问题：{q}\n\n文档列表：\n{doc_list}"}],
        )
        relevant_idx = set(_as_int_list(result.get("relevant")))

        graded: list[GradedChunk] = []
        for i, r in enumerate(results):
            graded.append(
                {
                    **r,
                    "relevant": i in relevant_idx,
                    "reason": result.get("reason", ""),
                }
            )

        n_rel = sum(1 for g in graded if g["relevant"])
        feedback = f"{n_rel}/{len(graded)} 个文档相关" if n_rel else "无相关文档，检索方向可能不对"
        return {
            **state,
            "graded": graded,
            "last_grade_feedback": feedback,
            "trace": state.get("trace", [])
            + [{"step": "grade_docs", "query": q, "relevant": n_rel, "total": len(graded)}],
        }

    return grade_documents


def make_grade_answer(llm: LLMCallFn):
    def grade_answer(state: AgenticState) -> AgenticState:
        if not state.get("answer") or not state.get("context"):
            return {**state, "answer_grounded": True}
        result = llm_json(
            llm,
            GRADE_ANSWER_SYSTEM,
            [
                {
                    "role": "user",
                    "content": (
                        f"问题：{state['query']}\n\n"
                        f"上下文：\n{state['context'][:3000]}\n\n"
                        f"答案：\n{state['answer'][:2000]}"
                    ),
                }
            ],
        )
        grounded = bool(result.get("grounded", True))
        return {
            **state,
            "answer_grounded": grounded,
            "trace": state.get("trace", [])
            + [
                {
                    "step": "grade_answer",
                    "grounded": grounded,
                    "reason": result.get("reason", ""),
                }
            ],
        }

    return grade_answer
