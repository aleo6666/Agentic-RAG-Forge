"""LLM-powered answer generation with citation support."""

from ragforge.config import get_config


def generate_answer(query: str, context: str) -> tuple[str, list[dict]]:
    """Generate an answer grounded in the provided context.

    Returns (answer_text, citations_list).
    Each citation = {"source": doc_id, "snippet": relevant_text}.
    """
    cfg = get_config()
    import httpx

    prompt = _build_prompt(query, context)

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
    return answer, citations


def _build_prompt(query: str, context: str) -> str:
    return f"""基于以下上下文回答问题。如果上下文不足，请明确说明。

上下文：
{context}

问题：{query}

请用中文回答，引用具体的上下文来源。"""


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
