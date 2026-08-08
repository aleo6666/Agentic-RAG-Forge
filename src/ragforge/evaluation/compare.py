"""Deterministic vs Agentic RAG comparison — LLM-as-judge evaluation.

Aligns with RAGAS metric semantics but uses the project's own LLM (DeepSeek)
as the judge, so no extra dependencies and no RAGAS/langchain version risk:

  - faithfulness:      every claim in the answer is supported by the context (0-1)
  - answer_relevancy:  the answer actually addresses the question (0-1)
  - usefulness:        how useful the answer is to a real user (0-1)
  - context_precision: fraction of retrieved contexts judged relevant (0-1)

Baseline contexts come from the deterministic pipeline (reranked top-5);
agentic contexts come from the LLM-graded relevant chunks. Comparing the two
shows the value of routing / grading / rewriting.
"""

from __future__ import annotations

import json
from typing import Callable

from ragforge.agentic.llm import LLMCallFn, default_llm, llm_json

JUDGE_ANSWER_SYSTEM = """你是 RAG 质量评审专家。基于【问题】、【上下文】、【回答】评估回答质量，只输出 JSON：
{"faithfulness": 0到1的小数, "answer_relevancy": 0到1的小数, "usefulness": 0到1的小数, "reason": "一句话说明"}
评分标准：
- faithfulness（忠实度）：回答中的每个论断是否都能从上下文找到依据。编造内容、脱离上下文 → 低分。
  重要：如果回答诚实说明"上下文没有该信息"且没有编造任何内容，faithfulness 应为 1.0。
- answer_relevancy（相关性）：回答是否直接针对问题、没有跑题或回避。
- usefulness（实用性）：对真实用户而言，这个回答是否完整、可操作、解决了问题。
  注意：诚实回答"没有该信息"但给出合理后续建议（如何获取信息等），实用性应高于直接拒绝。"""

JUDGE_CONTEXT_SYSTEM = """你是检索质量评审。判断给定文档是否与用户问题相关。
文档按编号列出，只输出 JSON：
{"relevant": [相关文档的编号数组], "irrelevant": [不相关文档的编号数组], "reason": "一句话说明"}"""


def _as_int_list(raw) -> list[int]:
    out = []
    for item in raw or []:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _doc_of(chunk: dict) -> tuple[str, str]:
    """Return (doc_id, filename) of a retrieved chunk for ground-truth matching."""
    c = chunk.get("chunk", chunk)
    meta = c.get("metadata") or {}
    return meta.get("doc_id", "") or c.get("doc_id", ""), meta.get("filename", "")


def mrr_hit_at_k(chunks: list[dict], expected_docs: list[str], k: int = 3) -> tuple[float | None, bool | None]:
    """MRR + Hit@k against ground-truth doc list. Returns (None, None) for negative samples."""
    if not expected_docs:
        return None, None
    expected = set(expected_docs)
    for rank, item in enumerate(chunks, start=1):
        doc_id, fname = _doc_of(item)
        if doc_id in expected or fname in expected:
            return round(1.0 / rank, 4), rank <= k
    return 0.0, False


def judge_answer(question: str, answer: str, contexts: list[str], llm: LLMCallFn | None = None) -> dict:
    """Score an answer against its context with the LLM judge."""
    llm = llm or default_llm
    context_text = "\n\n---\n\n".join(c[:800] for c in contexts[:5]) or "（无上下文）"
    result = llm_json(
        llm,
        JUDGE_ANSWER_SYSTEM,
        [
            {
                "role": "user",
                "content": (
                    f"【问题】\n{question}\n\n"
                    f"【上下文】\n{context_text}\n\n"
                    f"【回答】\n{answer[:2000]}"
                ),
            }
        ],
    )
    return {
        "faithfulness": round(float(result.get("faithfulness", 0)), 4),
        "answer_relevancy": round(float(result.get("answer_relevancy", 0)), 4),
        "usefulness": round(float(result.get("usefulness", 0)), 4),
        "reason": result.get("reason", ""),
    }


def judge_context_precision(question: str, contexts: list[str], llm: LLMCallFn | None = None) -> float:
    """Fraction of contexts the judge considers relevant to the question."""
    if not contexts:
        return 0.0
    llm = llm or default_llm
    doc_list = "\n\n".join(f"[{i}] {c[:2000]}" for i, c in enumerate(contexts))
    result = llm_json(
        llm,
        JUDGE_CONTEXT_SYSTEM,
        [{"role": "user", "content": f"问题：{question}\n\n文档列表：\n{doc_list}"}],
    )
    relevant = set(_as_int_list(result.get("relevant")))
    return round(len(relevant) / len(contexts), 4)


def run_comparison(
    questions: list[dict],
    tenant_id: str = "default",
    max_rounds: int = 3,
    llm: LLMCallFn | None = None,
) -> list[dict]:
    """Run both pipelines on each question and score with the judge.

    questions: [{"question": str, "note": str}]
    Returns per-question comparison records.
    """
    from ragforge.pipeline import run_query
    from ragforge.agentic.agentic_pipeline import run_agentic_query

    llm = llm or default_llm
    results = []

    for item in questions:
        q = item["question"]
        note = item.get("note", "")

        # ── Baseline: deterministic pipeline ──
        base_state = run_query(q, tenant_id=tenant_id)
        base_chunks = base_state.get("reranked", [])[:5]
        base_contexts = [r["chunk"]["content"] for r in base_chunks]
        base_answer = base_state.get("answer", "")
        base_metrics = judge_answer(q, base_answer, base_contexts, llm=llm)
        base_metrics["context_precision"] = judge_context_precision(q, base_contexts, llm=llm)
        base_mrr, base_hit = mrr_hit_at_k(base_chunks, item.get("expected_docs", []))

        # ── Agentic pipeline ──
        ag_state = run_agentic_query(q, tenant_id=tenant_id, max_rounds=max_rounds)
        ag_graded = ag_state.get("graded", [])
        if ag_graded:
            relevant = [g for g in ag_graded if g.get("relevant")]
            ag_chunks = relevant or ag_graded
            ag_contexts = [g["chunk"]["content"] for g in ag_chunks]
        else:
            # clarify best-effort / fallback 路径没有 graded — 从 state["context"] 还原
            ag_chunks = []
            ag_contexts = [c for c in ag_state.get("context", "").split("\n\n---\n\n") if c.strip()]
        ag_answer = ag_state.get("answer", "")
        ag_metrics = judge_answer(q, ag_answer, ag_contexts, llm=llm)
        ag_metrics["context_precision"] = judge_context_precision(q, ag_contexts, llm=llm)
        ag_mrr, ag_hit = mrr_hit_at_k(ag_chunks, item.get("expected_docs", []))

        results.append(
            {
                "question": q,
                "note": note,
                "expected_docs": item.get("expected_docs", []),
                "agent_trace": [t["step"] for t in ag_state.get("trace", [])],
                "baseline": {
                    "answer": base_answer,
                    "contexts": len(base_contexts),
                    "metrics": base_metrics,
                    "mrr": base_mrr,
                    "hit_at_k": base_hit,
                },
                "agentic": {
                    "answer": ag_answer,
                    "contexts": len(ag_contexts),
                    "metrics": ag_metrics,
                    "mrr": ag_mrr,
                    "hit_at_k": ag_hit,
                },
            }
        )

    return results


def format_report(results: list[dict]) -> str:
    """Render the comparison as a markdown report."""
    lines = ["# RAG Forge — 确定性 vs Agentic RAG 对比评估\n"]
    lines.append("| # | 问题 | 管线 | Faith | Rel | Use | CtxP | MRR | Hit@3 | 检索ctx |")
    lines.append("|---|------|------|-------|-----|-----|------|-----|-------|--------|")

    rows = []
    base_avg = {"faithfulness": [], "answer_relevancy": [], "usefulness": [], "context_precision": [], "mrr": [], "hit": []}
    ag_avg = {k: [] for k in base_avg}

    for i, r in enumerate(results, 1):
        for tag, rec, avg in (("基础", r["baseline"], base_avg), ("Agent", r["agentic"], ag_avg)):
            m = rec["metrics"]
            for k in ("faithfulness", "answer_relevancy", "usefulness", "context_precision"):
                avg[k].append(m[k])
            if rec.get("mrr") is not None:
                avg["mrr"].append(rec["mrr"])
            if rec.get("hit_at_k") is not None:
                avg["hit"].append(1 if rec["hit_at_k"] else 0)
            mrr = f"{rec['mrr']:.2f}" if rec.get("mrr") is not None else "—"
            hit = "✓" if rec.get("hit_at_k") else ("✗" if rec.get("hit_at_k") is not None else "—")
            rows.append(
                f"| {i} | {r['question'][:24]} | {tag} | {m['faithfulness']:.2f} | "
                f"{m['answer_relevancy']:.2f} | {m['usefulness']:.2f} | {m['context_precision']:.2f} | "
                f"{mrr} | {hit} | {rec['contexts']} |"
            )

    lines.extend(rows)
    lines.append("")

    def _avg(lst):
        return round(sum(lst) / len(lst), 4) if lst else 0.0

    lines.append("| **平均** | | **基础** | "
                 f"{_avg(base_avg['faithfulness']):.2f} | {_avg(base_avg['answer_relevancy']):.2f} | "
                 f"{_avg(base_avg['usefulness']):.2f} | {_avg(base_avg['context_precision']):.2f} | "
                 f"{_avg(base_avg['mrr']):.2f} | {round(_avg(base_avg['hit']), 2)} | |")
    lines.append("| | | **Agent** | "
                 f"{_avg(ag_avg['faithfulness']):.2f} | {_avg(ag_avg['answer_relevancy']):.2f} | "
                 f"{_avg(ag_avg['usefulness']):.2f} | {_avg(ag_avg['context_precision']):.2f} | "
                 f"{_avg(ag_avg['mrr']):.2f} | {round(_avg(ag_avg['hit']), 2)} | |")
    lines.append("")

    for i, r in enumerate(results, 1):
        lines.append(f"**Q{i}** ({r['note']}): {r['question']}")
        lines.append(f"- 期望文档: {', '.join(r.get('expected_docs', [])) or '（无，负样本）'}")
        lines.append(f"- 决策轨迹: {' → '.join(r['agent_trace'])}")
        base_reason = r["baseline"]["metrics"]["reason"]
        ag_reason = r["agentic"]["metrics"]["reason"]
        lines.append(f"  - 基础: {base_reason}")
        lines.append(f"  - Agent: {ag_reason}")

    return "\n".join(lines)
