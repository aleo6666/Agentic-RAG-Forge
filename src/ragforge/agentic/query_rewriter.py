"""Query rewriting — turns a failed retrieval round into a better search query."""

from ragforge.agentic.llm import LLMCallFn, llm_json
from ragforge.agentic.agentic_state import AgenticState

REWRITE_SYSTEM = """你是检索查询改写专家。用户问题经过一轮检索没有得到满意的相关文档，请改写为更适合向量检索与关键词检索的查询。
要求：
- 保留核心语义，补充关键实体、同义词、限定词
- 输出单个最佳查询（与原始问题同语言）
只输出 JSON，格式：{"query": "改写后的查询", "reason": "一句话改写理由"}"""


def make_rewrite_query(llm: LLMCallFn):
    def rewrite_query(state: AgenticState) -> AgenticState:
        q = state["query"]
        prev = state.get("rewritten_query") or q
        feedback = state.get("last_grade_feedback", "未说明")
        result = llm_json(
            llm,
            REWRITE_SYSTEM,
            [
                {
                    "role": "user",
                    "content": (
                        f"原始问题：{q}\n"
                        f"上一轮检索查询：{prev}\n"
                        f"上一轮检索不足的原因：{feedback}"
                    ),
                }
            ],
        )
        new_q = (result.get("query") or prev).strip()
        return {
            **state,
            "rewritten_query": new_q,
            "trace": state.get("trace", [])
            + [
                {
                    "step": "rewrite",
                    "query": q,
                    "rewritten": new_q,
                    "reason": result.get("reason", ""),
                }
            ],
        }

    return rewrite_query
