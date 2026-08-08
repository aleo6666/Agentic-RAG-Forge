"""Agentic RAG tests — inject fakes for LLM/retriever/generator, verify the graph logic.

No network, no vector store: every external dependency is swapped for a fake
via build_agentic_pipeline(deps). These tests prove the *decisions*:
routing, grading, rewrite loops, grounding checks, round budgets.
"""

import sys, os
sys.path.insert(0, "src")

os.environ["DEEPSEEK_API_KEY"] = "sk-test"

import pytest

from ragforge.agentic.agentic_pipeline import build_agentic_pipeline


# ── Fakes ───────────────────────────────────────────────────────

class FakeLLM:
    """Queue-based fake: pops a canned JSON response per call."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, list]] = []  # (system, messages)

    def __call__(self, messages, system, temperature=0.0):
        self.calls.append((system, messages))
        if self._responses:
            return self._responses.pop(0)
        return '{"action": "direct", "reason": "fallback"}'

    @property
    def systems(self) -> list[str]:
        return [s for s, _ in self.calls]


def chunk(content: str, cid: str = "c1") -> dict:
    return {
        "chunk": {"id": cid, "content": content, "doc_id": "d1", "metadata": {}},
        "score": 0.9,
        "source": "hybrid",
    }


def make_retriever(*batches):
    """Returns (retriever, seen_queries). Each call pops the next batch of chunks."""
    queue = [list(b) for b in batches]
    seen = []

    def retriever(query, tenant_id, top_k=20):
        seen.append(query)
        return queue.pop(0) if queue else []

    return retriever, seen


def fake_reranker(query, retrieved, top_k=5):
    return retrieved[:top_k]


def fake_generator(query, context):
    return "基于上下文的测试答案。", [{"source": "chunk_0", "snippet": context[:60]}]


def run_with(llm, batches, **kw):
    retriever, seen = make_retriever(*batches)
    graph = build_agentic_pipeline(
        llm=llm,
        retriever=retriever,
        reranker=fake_reranker,
        generator=fake_generator,
        **kw,
    ).compile()
    return graph.invoke(
        {"query": "测试问题", "tenant_id": "test", "retrieval_rounds": 0, "max_rounds": 3, "trace": []}
    ), seen


# ── Tests ───────────────────────────────────────────────────────

def test_happy_path_retrieve_generate():
    """route=retrieve → all docs relevant → generate → grounded → END (no loops)."""
    llm = FakeLLM([
        '{"action": "retrieve", "reason": "需要知识库"}',
        '{"relevant": [0, 1], "irrelevant": [2], "reason": "前两个相关"}',
        '{"grounded": true, "reason": "答案有依据"}',
    ])
    state, seen = run_with(llm, [[chunk("文档A内容", "a"), chunk("文档B内容", "b"), chunk("文档C内容", "c")]])

    steps = [t["step"] for t in state["trace"]]
    assert steps == ["route", "retrieve", "grade_docs", "generate", "grade_answer"]
    assert state["answer"] == "基于上下文的测试答案。"
    assert state["answer_grounded"] is True
    assert len(seen) == 1  # 只检索一次


def test_rewrite_loop_when_nothing_relevant():
    """First retrieval round finds nothing relevant → rewrite → re-retrieve → succeed."""
    llm = FakeLLM([
        '{"action": "retrieve", "reason": "需要知识库"}',
        '{"relevant": [], "irrelevant": [0], "reason": "检索方向不对"}',          # grade round 1
        '{"query": "改写后的查询：LangGraph 部署", "reason": "补充关键词"}',       # rewrite
        '{"relevant": [0], "irrelevant": [], "reason": "改写后命中"}',            # grade round 2
        '{"grounded": true, "reason": "有依据"}',
    ])
    state, seen = run_with(
        llm,
        [
            [chunk("不相关内容", "x")],        # round 1 batch
            [chunk("LangGraph 部署相关内容", "y")],  # round 2 batch
        ],
    )

    steps = [t["step"] for t in state["trace"]]
    assert steps == ["route", "retrieve", "grade_docs", "rewrite", "retrieve", "grade_docs", "generate", "grade_answer"]
    assert len(seen) == 2  # 检索了两轮
    assert state["retrieval_rounds"] == 2
    assert state["rewritten_query"] == "改写后的查询：LangGraph 部署"
    assert state["answer_grounded"] is True


def test_answer_not_grounded_triggers_rewrite_loop():
    """generate → grade_answer says not grounded → rewrite → re-retrieve → regenerate."""
    llm = FakeLLM([
        '{"action": "retrieve", "reason": "需要知识库"}',
        '{"relevant": [0], "irrelevant": [], "reason": "相关"}',
        '{"grounded": false, "reason": "答案编造了上下文没有的内容"}',   # answer grade round 1
        '{"query": "更精确的查询", "reason": "需要更多细节"}',
        '{"relevant": [0], "irrelevant": [], "reason": "命中"}',
        '{"grounded": true, "reason": "现在有依据了"}',
    ])
    state, seen = run_with(
        llm,
        [
            [chunk("初步内容", "p")],
            [chunk("补充细节内容", "q")],
        ],
    )

    steps = [t["step"] for t in state["trace"]]
    assert "rewrite" in steps
    assert steps.count("retrieve") == 2
    assert steps.count("generate") == 2
    assert state["answer_grounded"] is True
    assert len(seen) == 2


def test_max_rounds_budget_graceful_degrade():
    """Nothing is ever relevant → after max_rounds retrievals, still generates (no infinite loop)."""
    llm = FakeLLM([
        '{"action": "retrieve", "reason": "需要知识库"}',
        '{"relevant": [], "irrelevant": [0], "reason": "无关"}',   # grade 1
        '{"query": "改写1", "reason": "再试"}',
        '{"relevant": [], "irrelevant": [0], "reason": "仍无关"}',  # grade 2
        '{"query": "改写2", "reason": "再试"}',
        '{"relevant": [], "irrelevant": [0], "reason": "还是无关"}', # grade 3 → 触顶
    ])
    state, seen = run_with(
        llm,
        [[chunk("无关1", "n1")], [chunk("无关2", "n2")], [chunk("无关3", "n3")]],
        max_rounds=3,
    )

    steps = [t["step"] for t in state["trace"]]
    assert steps.count("retrieve") == 3
    assert steps.count("rewrite") == 2  # 第3轮触顶后不再改写
    assert steps[-1] == "grade_answer"
    assert state["retrieval_rounds"] == 3
    # 兜底生成仍发生
    assert "generate" in steps


def test_direct_answer_without_retrieval():
    """route=direct → LLM answers, retriever never called."""
    llm = FakeLLM([
        '{"action": "direct", "reason": "闲聊"}',
        "你好！我是知识库助手，很高兴见到你。",
    ])
    state, seen = run_with(llm, [[chunk("不应被检索", "x")]])

    steps = [t["step"] for t in state["trace"]]
    assert steps == ["route", "direct"]
    assert seen == []  # 检索从未发生
    assert state["answer"] == "你好！我是知识库助手，很高兴见到你。"


def test_clarify_when_question_vague():
    """route=clarify → returns the clarification question when retrieval finds nothing."""
    llm = FakeLLM(['{"action": "clarify", "reason": "问题模糊", "clarification": "请说明你想查哪份文档？"}'])
    state, seen = run_with(llm, [[]])  # 空检索结果 → 纯澄清

    steps = [t["step"] for t in state["trace"]]
    assert steps == ["route", "clarify"]
    assert seen == ["测试问题"]  # best-effort 尝试了一次检索
    assert state["answer"] == "请说明你想查哪份文档？"


def test_clarify_best_effort_answer():
    """route=clarify but retrieval finds content → answer with clarification prefix."""
    llm = FakeLLM(['{"action": "clarify", "reason": "问题模糊", "clarification": "请说明部署环境"}'])
    state, seen = run_with(llm, [[chunk("部署相关文档内容", "d")]])

    steps = [t["step"] for t in state["trace"]]
    assert steps == ["route", "clarify"]
    assert "基于已有资料尝试回答" in state["answer"]
    assert "基于上下文的测试答案" in state["answer"]  # fake generator 的输出
    assert state["citations"]  # 有引用


def test_graph_compiles_with_default_deps():
    """The production graph (real deps) still compiles — import & wiring sanity."""
    graph = build_agentic_pipeline()
    compiled = graph.compile()
    assert compiled is not None


def test_llm_json_parse_tolerates_fences():
    from ragforge.agentic.llm import parse_json_response

    assert parse_json_response('{"a": 1}') == {"a": 1}
    assert parse_json_response('```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json_response('好的，结果如下：{"a": 3} 就是这样') == {"a": 3}
