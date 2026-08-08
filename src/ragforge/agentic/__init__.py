"""Agentic RAG layer — routing, grading, query rewriting and self-reflection loops.

Built on top of the deterministic pipeline: hybrid retrieval + reranker + generator
stay untouched; this layer adds LLM-driven decisions around them.
"""

from ragforge.agentic.agentic_pipeline import build_agentic_pipeline, run_agentic_query

__all__ = ["build_agentic_pipeline", "run_agentic_query"]
