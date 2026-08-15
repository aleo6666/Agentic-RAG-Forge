"""LLM-powered answer generation with citation support."""

from ragforge.config import get_config

CITATION_CHECK_SYSTEM = """你是引用校验器。用户给出【回答】和【引用片段】列表。
判断每个引用片段是否真实支撑回答中的论断（被回答实际使用、内容确实支撑）。
只输出 JSON：{"valid_indexes": [有效引用编号数组], "reason": "一句话说明"}
如果回答没有使用该片段的内容，或片段与论断无关，则该引用无效。"""


def generate_answer(
    query: str,
    context: str,
    history: list[dict] | None = None,
    citation_check: bool = False,
) -> tuple[str, list[dict]]:
    """Generate an answer grounded in the provided context.

    Returns (answer_text, citations_list).
    Each citation = {"source": doc_id, "snippet": relevant_text}.
    ``history`` is an optional list of prior turns
    ``[{"role": "user"/"assistant", "content": ...}]`` — injected into the
    prompt so the answer can reference earlier conversation context.
    When citation_check=True, citations are LLM-validated — hallucinated or
    unused references are filtered out (one extra LLM call).
    """
    cfg = get_config()
    import httpx

    prompt = _build_prompt(query, context, history=history)

    resp = httpx.post(
        f"{cfg.llm_endpoint}/chat/completions",
        headers={"Authorization": f"Bearer {cfg.llm_api_key}"},
        json={
            "model": cfg.llm_model,
            "messages": [
                {"role": "system", "content": "你是知识库助手。只基于提供的上下文回答问题，引用来源。不要补充上下文之外的知识；如果上下文不足，明确说明无法回答或信息不完整。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
        },
        timeout=60,
    )
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"]

    # Extract citations from context
    citations = _extract_citations(answer, context)
    if citation_check:
        from ragforge.agentic.llm import default_llm, llm_json

        citations = _validate_citations(answer, citations, llm_json, default_llm)
    return answer, citations


def _validate_citations(answer: str, citations: list[dict], llm_json, llm) -> list[dict]:
    """LLM 校验每个引用是否真实支撑回答论断，剔除幻觉引用。"""
    if not citations:
        return citations
    doc_list = "\n\n".join(f"[{i}] {c['snippet']}" for i, c in enumerate(citations))
    result = llm_json(
        llm,
        CITATION_CHECK_SYSTEM,
        [{"role": "user", "content": f"【回答】\n{answer[:2000]}\n\n【引用片段】\n{doc_list}"}],
    )
    valid = set()
    for item in result.get("valid_indexes", []):
        try:
            valid.add(int(item))
        except (TypeError, ValueError):
            continue
    return [c for i, c in enumerate(citations) if i in valid]


def _build_prompt(query: str, context: str, history: list[dict] | None = None) -> str:
    sections = ["基于以下上下文回答问题。如果上下文不足，请明确说明。"]
    if history:
        sections.append(_format_history(history))
    sections.append(f"上下文：\n{context}")
    sections.append(f"问题：{query}")
    sections.append("请用中文回答，引用具体的上下文来源。")
    return "\n\n".join(sections)


def _format_history(history: list[dict]) -> str:
    """Render alternating user/assistant turns as a readable dialogue block."""
    lines = ["对话历史（本轮问题之前）："]
    for msg in history:
        label = "用户" if msg.get("role") == "user" else "助手"
        lines.append(f"{label}：{msg.get('content', '')}")
    return "\n".join(lines)


def _extract_citations(answer: str, context: str) -> list[dict]:
    """Find which chunks of context appear in the answer."""
    chunks = context.split("\n\n---\n\n")
    cited = []
    for i, chunk in enumerate(chunks):
        # Simple overlap check — first 30 chars as snippet fingerprint
        snippet = chunk[:80].strip()
        if snippet and snippet[:30] in answer:
            cited.append({"source": f"chunk_{i}", "snippet": snippet})
    return cited
