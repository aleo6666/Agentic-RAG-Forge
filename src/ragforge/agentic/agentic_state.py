"""Agentic RAG graph state."""

from typing import TypedDict, Literal

from ragforge.pipeline import RetrievedChunk


class GradedChunk(TypedDict):
    """A retrieved chunk with an LLM relevance verdict."""

    chunk: dict
    score: float
    source: str
    relevant: bool
    reason: str


class AgenticState(TypedDict, total=False):
    """State flowing through the agentic graph."""

    # Input
    query: str
    tenant_id: str

    # Agent decisions
    route_decision: Literal["retrieve", "direct", "clarify"]
    clarification: str
    rewritten_query: str
    retrieval_rounds: int
    max_rounds: int

    # Retrieval artifacts
    retrieved: list[RetrievedChunk]
    graded: list[GradedChunk]
    context: str

    # Output
    answer: str
    citations: list[dict]
    answer_grounded: bool

    # Audit trail — every decision the agent made, in order
    trace: list[dict]
    errors: list[str]
