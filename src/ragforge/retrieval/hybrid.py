"""Hybrid retrieval: dense + BM25 → Reciprocal Rank Fusion (RRF)."""

from ..pipeline import RetrievedChunk, Chunk


def hybrid_retrieve(query: str, tenant_id: str, top_k: int = 20) -> list[RetrievedChunk]:
    """Two-stage retrieval: dense vectors + BM25 keywords → RRF merge."""
    from ragforge.indexing.vector_store import search_dense, _get_collection

    # Convert dense results (list[tuple[id,score]]) to list[RetrievedChunk]
    dense_raw = search_dense(query, tenant_id, top_k=top_k)
    collection = _get_collection(tenant_id)
    all_data = collection.get(ids=[rid for rid, _ in dense_raw]) if dense_raw else {"documents": [], "metadatas": []}
    dense_results = [
        {
            "chunk": {
                "id": rid,
                "content": all_data["documents"][i] if i < len(all_data["documents"]) else "",
                "doc_id": all_data["metadatas"][i].get("doc_id", "") if i < len(all_data["metadatas"]) else "",
                "metadata": all_data["metadatas"][i] if i < len(all_data["metadatas"]) else {},
            },
            "score": score,
            "source": "dense",
        }
        for i, (rid, score) in enumerate(dense_raw)
    ]

    sparse_results = search_sparse(query, tenant_id, top_k=top_k)

    # Reciprocal Rank Fusion
    fused = _rrf_fuse(dense_results, sparse_results, k=60)
    return fused[:top_k]


def search_sparse(query: str, tenant_id: str, top_k: int = 20) -> list[RetrievedChunk]:
    """BM25 keyword search over indexed chunks."""
    from ragforge.indexing.vector_store import _get_collection
    from rank_bm25 import BM25Okapi

    collection = _get_collection(tenant_id)
    all_data = collection.get()
    if not all_data["ids"]:
        return []

    docs = all_data["documents"] or []
    ids = all_data["ids"]
    metadatas = all_data.get("metadatas", [{}] * len(docs))
    tokenized = [d.split() for d in docs]
    bm25 = BM25Okapi(tokenized)

    scores = bm25.get_scores(query.split())

    # Sort by score and pair with doc index
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    return [
        {
            "chunk": {
                "id": ids[idx],
                "content": docs[idx],
                "doc_id": metadatas[idx].get("doc_id", ""),
                "metadata": metadatas[idx],
            },
            "score": score,
            "source": "sparse",
        }
        for idx, score in ranked
    ]


def _rrf_fuse(
    dense: list[RetrievedChunk],
    sparse: list[RetrievedChunk],
    k: int = 60,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion: combine dense + sparse results."""
    scores: dict[str, float] = {}

    for rank, item in enumerate(dense):
        scores[item["chunk"]["id"]] = 1.0 / (k + rank + 1)
    for rank, item in enumerate(sparse):
        cid = item["chunk"]["id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    lookup = {}
    for item in dense + sparse:
        if item["chunk"]["id"] not in lookup:
            lookup[item["chunk"]["id"]] = item

    return [
        {**lookup[cid], "score": s, "source": "hybrid"}
        for cid, s in merged
        if cid in lookup
    ]
