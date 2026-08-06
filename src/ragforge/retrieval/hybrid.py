"""Hybrid retrieval: dense + BM25 → Reciprocal Rank Fusion (RRF)."""

from ..pipeline import RetrievedChunk, Chunk


def hybrid_retrieve(query: str, tenant_id: str, top_k: int = 20) -> list[RetrievedChunk]:
    """Two-stage retrieval: dense vectors + BM25 keywords → RRF merge."""
    from ragforge.indexing.vector_store import search_dense
    from ragforge.retrieval.hybrid import search_sparse

    dense_results = search_dense(query, tenant_id, top_k=top_k)
    sparse_results = search_sparse(query, tenant_id, top_k=top_k)

    # Reciprocal Rank Fusion
    fused = _rrf_fuse(dense_results, sparse_results, k=60)
    return fused[:top_k]


def search_sparse(query: str, tenant_id: str, top_k: int = 20) -> list[RetrievedChunk]:
    """BM25 keyword search over indexed chunks."""
    from ragforge.indexing.vector_store import _get_collection
    from rank_bm25 import BM25Okapi

    collection = _get_collection(tenant_id)
    # Fetch all docs from the collection for BM25 indexing
    all_data = collection.get()
    if not all_data["ids"]:
        return []

    # Tokenize for BM25
    docs = all_data["documents"] or []
    tokenized = [d.split() for d in docs]
    bm25 = BM25Okapi(tokenized)

    query_tokens = query.split()
    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        zip(all_data["ids"], scores, all_data.get("metadatas", [{}] * len(docs))),
        key=lambda x: x[1],
        reverse=True,
    )[:top_k]

    return [
        {
            "chunk": {
                "id": rid,
                "content": docs[i] if i < len(docs) else "",
                "doc_id": meta.get("doc_id", ""),
                "metadata": meta,
            },
            "score": score,
            "source": "sparse",
        }
        for i, (rid, score, meta) in enumerate(ranked)
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

    # Build lookup from original items
    lookup = {}
    for item in dense + sparse:
        if item["chunk"]["id"] not in lookup:
            lookup[item["chunk"]["id"]] = item

    return [
        {**lookup[cid], "score": s, "source": "hybrid"}
        for cid, s in merged
        if cid in lookup
    ]
