"""Reranking with cross-encoder for improved retrieval precision."""

from ..pipeline import RetrievedChunk
from ragforge.config import get_config


_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        cfg = get_config()
        _reranker = CrossEncoder(cfg.reranker_model)
    return _reranker


def rerank_chunks(query: str, retrieved: list[RetrievedChunk], top_k: int = 5) -> list[RetrievedChunk]:
    """Rerank retrieved chunks using a cross-encoder.

    Takes the top-N dense+sparse results and re-ranks them
    for precision, returning the best `top_k`.
    """
    if not retrieved:
        return []

    reranker = _get_reranker()
    pairs = [(query, r["chunk"]["content"]) for r in retrieved]
    scores = reranker.predict(pairs)

    ranked = sorted(zip(retrieved, scores), key=lambda x: x[1], reverse=True)
    return [
        {**item, "score": float(score)}
        for item, score in ranked[:top_k]
    ]
