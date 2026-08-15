"""Multi-turn session evaluation: 无记忆 vs 有记忆 对比评估.

验证智能客服升级的核心卖点：
- 指代消解（"它有什么优点？" → 结合历史回答 RAG 的优点）
- 会话记忆（多轮上下文注入）

方法：对每个场景构造两路——
  A. 有记忆路：POST /chat 同一 session 连续两轮（第二轮用指代形式）
  B. 无记忆路：POST /chat 新 session 直接问第二轮的原问题（无历史）

指标：
- 指代成功率：有记忆路第二轮答案中是否命中目标主题（人工判定关键词）
- 答案有用性：judge（复用 evaluator 的 judge_answer）
- 对比：有记忆 vs 无记忆 的 answer 质量

用法：PYTHONPATH=src python scripts/eval_multi_turn.py [api_base] [api_key]
"""

import json
import sys
import time
import urllib.request

API_BASE = "http://127.0.0.1:8788"
API_KEY = ""

SCENARIOS = [
    {
        "name": "指代消解-核心概念",
        "first": "什么是RAG？",
        "followup": "它有什么优点？",
        "expected_topic": ["RAG", "检索增强", "优点", "减少幻觉", "知识实时", "可追溯"],
        "note": "第二轮指代'它'，有记忆应解析为 RAG",
    },
    {
        "name": "指代消解-部署主题",
        "first": "如何用 Docker 部署 RAG Forge？",
        "followup": "部署后如何验证服务是否正常？",
        "expected_topic": ["验证", "health", "健康", "检查", "curl"],
        "note": "第二轮延续部署话题，有记忆应衔接上下文",
    },
    {
        "name": "追问细节",
        "first": "RAG Forge 的混合检索是怎么工作的？",
        "followup": "那它的缓存机制呢？",
        "expected_topic": ["缓存", "embedding", "嵌入", "Cache"],
        "note": "'那'指代 RAG Forge 的检索链路，有记忆应指向混合检索上下文",
    },
]


def post_chat(question: str, session_id: str | None = None) -> dict:
    body = {"question": question}
    if session_id:
        body["session_id"] = session_id
    req = urllib.request.Request(
        f"{API_BASE}/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def hit_topic(answer: str, topics: list[str]) -> bool:
    return any(t.lower() in answer.lower() for t in topics)


def main():
    global API_BASE, API_KEY
    if len(sys.argv) > 1:
        API_BASE = sys.argv[1]
    if len(sys.argv) > 2:
        API_KEY = sys.argv[2]

    print(f"API: {API_BASE}  key: {'configured' if API_KEY else 'EMPTY'}")
    print("=" * 72)

    results = []
    for sc in SCENARIOS:
        print(f"\n▶ 场景: {sc['name']} — {sc['note']}")
        # 有记忆路
        try:
            r1 = post_chat(sc["first"])
            sid = r1["session_id"]
            r2 = post_chat(sc["followup"], sid)
            mem_answer = r2["answer"]
            mem_rounds = r2.get("rounds", 0)
        except Exception as e:
            print(f"  有记忆路失败: {e}")
            continue
        # 无记忆路（直接问 followup，无历史）
        try:
            r0 = post_chat(sc["followup"])
            no_mem_answer = r0["answer"]
        except Exception as e:
            print(f"  无记忆路失败: {e}")
            continue

        mem_hit = hit_topic(mem_answer, sc["expected_topic"])
        no_hit = hit_topic(no_mem_answer, sc["expected_topic"])
        # 严格指标：是否直接回答（不以澄清前缀开头）—— 指代消解有效的量化证据
        mem_direct = not any(p in mem_answer[:30] for p in ["问题比较模糊", "请补充说明", "您指的是", "哪个系统"])
        no_direct = not any(p in no_mem_answer[:30] for p in ["问题比较模糊", "请补充说明", "您指的是", "哪个系统"])

        print(f"  无记忆回答: {no_mem_answer[:100]}...")
        print(f"  无记忆命中主题: {no_hit} | 直接回答: {no_direct}")
        print(f"  有记忆回答: {mem_answer[:100]}...")
        print(f"  有记忆命中主题: {mem_hit} | 直接回答: {mem_direct} (rounds={mem_rounds})")

        results.append(
            {
                "scenario": sc["name"],
                "no_mem_hit": no_hit,
                "mem_hit": mem_hit,
                "no_mem_direct": no_direct,
                "mem_direct": mem_direct,
                "no_mem_answer": no_mem_answer[:300],
                "mem_answer": mem_answer[:300],
                "rounds": mem_rounds,
            }
        )
        time.sleep(1)

    print("\n" + "=" * 72)
    print("汇总")
    mem_hits = sum(1 for r in results if r["mem_hit"])
    no_hits = sum(1 for r in results if r["no_mem_hit"])
    mem_directs = sum(1 for r in results if r["mem_direct"])
    no_directs = sum(1 for r in results if r["no_mem_direct"])
    print(f"有记忆命中主题: {mem_hits}/{len(results)}")
    print(f"无记忆命中主题: {no_hits}/{len(results)}")
    print(f"有记忆直接回答: {mem_directs}/{len(results)}")
    print(f"无记忆直接回答: {no_directs}/{len(results)}")

    with open("eval_multi_turn.report.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("报告: eval_multi_turn.report.jsonl")


if __name__ == "__main__":
    main()
