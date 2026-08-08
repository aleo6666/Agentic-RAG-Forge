"""LLM helper for agentic nodes — structured JSON calls over the configured endpoint.

The agentic layer talks to the same OpenAI-compatible endpoint as the generator
(DeepSeek by default). Every node takes an injectable ``LLMCallFn`` so tests can
substitute a fake without touching the network.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from ragforge.config import get_config

# (messages, system, temperature) -> raw text
LLMCallFn = Callable[[list[dict], str, float], str]


def default_llm(messages: list[dict], system: str, temperature: float = 0.0) -> str:
    """Call the configured LLM and return raw text. Falls back without json mode if unsupported."""
    cfg = get_config()
    import httpx

    body = {
        "model": cfg.llm_model,
        "messages": [{"role": "system", "content": system}, *messages],
        "temperature": temperature,
        "max_tokens": 2048,
    }

    def _post(payload: dict) -> str:
        resp = httpx.post(
            f"{cfg.llm_endpoint}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.llm_api_key}"},
            json=payload,
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    try:
        return _post({**body, "response_format": {"type": "json_object"}})
    except Exception:
        # LM Studio and some proxies reject response_format — retry without it
        return _post(body)


def parse_json_response(text: str) -> dict:
    """Parse JSON from LLM output — tolerates markdown fences and trailing prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        block = re.search(r"\{.*\}", text, re.DOTALL)
        if block:
            return json.loads(block.group(0))
        raise


def llm_json(llm: LLMCallFn, system: str, messages: list[dict], temperature: float = 0.0) -> dict:
    """Call the LLM and parse its output as structured JSON."""
    text = llm(messages, system, temperature)
    return parse_json_response(text)
