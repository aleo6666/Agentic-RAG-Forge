"""Schema-less vector store backed by Chroma (default) or Qdrant."""

from ..pipeline import Chunk
from ragforge.indexing.embedder import get_embedding


_collections: dict[str, object] = {}  # tenant_id → collection


def _get_collection(tenant_id: str):
    """Get or create a Chroma collection scoped to the tenant."""
    if tenant_id not in _collections:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.Client(Settings(is_persistent=True, persist_directory="./chroma_data"))
        # Sanitize tenant_id for collection name
        name = f"ragforge_{tenant_id.replace('/', '_').replace('.', '_')}"
        _collections[tenant_id] = client.get_or_create_collection(name=name)
    return _collections[tenant_id]


def index_chunks(chunks: list[Chunk], tenant_id: str = "default", dedup: bool = True) -> dict:
    """Index chunks into the tenant's vector store — with DocumentHash incremental sync.

    Reuses pre-computed embeddings attached to chunk metadata by the embed node.
    When dedup=True (default):
      - unchanged chunks (same doc_id + same content hash) are skipped
      - changed/removed chunks of a known doc_id are deleted first
      - new chunks are added
    Returns {"added": n, "skipped": n, "removed": n}.
    """
    if not chunks:
        return {"added": 0, "skipped": 0, "removed": 0}

    from ragforge.cache.embedding_cache import fingerprint

    collection = _get_collection(tenant_id)

    # Hash every chunk of this batch, group by doc_id
    batch: dict[str, set[str]] = {}
    for c in chunks:
        c.setdefault("metadata", {})["doc_hash"] = fingerprint(c["content"])
        batch.setdefault(c.get("doc_id", ""), set()).add(c["metadata"]["doc_hash"])

    to_delete: list[str] = []
    existing_hashes: set[str] = set()
    if dedup:
        existing = collection.get(include=["metadatas"])
        for cid, meta in zip(existing.get("ids") or [], existing.get("metadatas") or []):
            meta = meta or {}
            if meta.get("doc_id", "") in batch:
                h = meta.get("doc_hash", "")
                existing_hashes.add(h)
                if h and h not in batch[meta["doc_id"]]:
                    to_delete.append(cid)  # content changed or was removed

    if to_delete:
        collection.delete(ids=to_delete)

    to_add = (
        [c for c in chunks if c["metadata"]["doc_hash"] not in existing_hashes]
        if dedup
        else chunks
    )
    if not to_add:
        return {"added": 0, "skipped": len(chunks), "removed": len(to_delete)}

    ids = [c["id"] for c in to_add]
    texts = [c["content"] for c in to_add]
    metadatas = [
        {
            **{k: v for k, v in c.get("metadata", {}).items() if k != "_embedding"},
            "doc_id": c.get("doc_id", ""),  # 顶层 doc_id 写入 metadata，供检索结果归属/MRR 计算
        }
        for c in to_add
    ]
    # Reuse attached embeddings; fall back to computing on the fly
    embeddings = [
        c.get("metadata", {}).get("_embedding") or get_embedding(c["content"])
        for c in to_add
    ]

    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
    return {"added": len(to_add), "skipped": len(chunks) - len(to_add), "removed": len(to_delete)}


def search_dense(query: str, tenant_id: str, top_k: int = 10) -> list[tuple[str, float]]:
    """Dense vector search."""
    collection = _get_collection(tenant_id)
    embedding = get_embedding(query)
    results = collection.query(query_embeddings=[embedding], n_results=top_k)
    ids = results["ids"][0] if results["ids"] else []
    distances = results["distances"][0] if results.get("distances") else [0] * len(ids)
    return list(zip(ids, [1.0 - d for d in distances]))  # distance → similarity


def remove_document(doc_id: str, tenant_id: str) -> int:
    """Remove all chunks of one document. Returns removed count.

    Incremental-sync counterpart of index_chunks: add/update go through
    index_chunks (idempotent, hash-dedup), delete goes through here — the
    batch-based delete inside index_chunks only handles in-batch changes.
    """
    collection = _get_collection(tenant_id)
    existing = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
    ids = existing.get("ids") or []
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def list_documents(tenant_id: str) -> list[dict]:
    """Aggregate indexed chunks by doc_id → per-document summary for the UI."""
    collection = _get_collection(tenant_id)
    data = collection.get()
    metas = data.get("metadatas") or []
    docs: dict[str, dict] = {}
    for m in metas:
        m = m or {}
        doc_id = m.get("doc_id") or m.get("filename") or "unknown"
        entry = docs.setdefault(
            doc_id,
            {
                "doc_id": doc_id,
                "filename": m.get("filename", doc_id),
                "chunks": 0,
                "chars": 0,
            },
        )
        entry["chunks"] += 1
        entry["chars"] += int(m.get("char_count") or 0)
    return list(docs.values())


def clear_documents(tenant_id: str) -> int:
    """Delete the tenant's whole collection. Returns removed chunk count."""
    import chromadb
    from chromadb.config import Settings

    collection = _get_collection(tenant_id)
    count = collection.count()

    client = chromadb.Client(Settings(is_persistent=True, persist_directory="./chroma_data"))
    name = f"ragforge_{tenant_id.replace('/', '_').replace('.', '_')}"
    try:
        client.delete_collection(name)
    except Exception:
        pass
    _collections.pop(tenant_id, None)  # drop cached handle — rebuilt on next access
    return count
