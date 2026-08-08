"""Query router — decides whether retrieval is needed at all.

Three-way decision:
  - retrieve: question needs the knowledge base
  - direct:   chit-chat / general knowledge → answer without retrieval
  - clarify:  question too vague → ask for clarification
"""

from ragforge.agentic.llm import LLMCallFn, llm_json
from ragforge.agentic.agentic_state import AgenticState

ROUTE_SYSTEM = """你是知识库检索路由。判断用户问题是否需要检索知识库。
规则：
- 问题涉及知识库内容、文档细节、项目资料 → action=retrieve。即使表述模糊、信息不全，只要主题与知识库相关就检索，检索不足由查询改写循环处理，不要轻易放弃。
- 纯闲聊、问候、与知识库无关的常识性问题 → action=direct
- 只有问题缺少核心对象、完全无法构造检索（如"那个东西怎么用？"）时 → action=clarify
只输出 JSON，格式：{"action": "retrieve"|"direct"|"clarify", "reason": "一句话理由", "clarification": "action=clarify 时给出澄清问题，否则空字符串"}"""


def make_route_query(llm: LLMCallFn):
    def route_query(state: AgenticState) -> AgenticState:
        q = state["query"]
        result = llm_json(
            llm,
            ROUTE_SYSTEM,
            [{"role": "user", "content": f"用户问题：{q}"}],
        )
        action = result.get("action", "retrieve")
        if action not in ("retrieve", "direct", "clarify"):
            action = "retrieve"
        return {
            **state,
            "route_decision": action,
            "clarification": result.get("clarification", ""),
            "trace": state.get("trace", [])
            + [
                {
                    "step": "route",
                    "query": q,
                    "decision": action,
                    "reason": result.get("reason", ""),
                }
            ],
        }

    return route_query
