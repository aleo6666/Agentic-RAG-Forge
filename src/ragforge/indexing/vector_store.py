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


def index_chunks(chunks: list[Chunk], tenant_id: str = "default") -> None:
    """Index chunks into the tenant's vector store.
    Reuses pre-computed embeddings attached to chunk metadata by the embed node.
    """
    if not chunks:
        return

    collection = _get_collection(tenant_id)
    ids = [c["id"] for c in chunks]
    texts = [c["content"] for c in chunks]
    metadatas = [
        {k: v for k, v in c.get("metadata", {}).items() if k != "_embedding"}
        for c in chunks
    ]
    # Reuse attached embeddings; fall back to computing on the fly
    embeddings = [
        c.get("metadata", {}).get("_embedding") or get_embedding(c["content"])
        for c in chunks
    ]

    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)


def search_dense(query: str, tenant_id: str, top_k: int = 10) -> list[tuple[str, float]]:
    """Dense vector search."""
    collection = _get_collection(tenant_id)
    embedding = get_embedding(query)
    results = collection.query(query_embeddings=[embedding], n_results=top_k)
    ids = results["ids"][0] if results["ids"] else []
    distances = results["distances"][0] if results.get("distances") else [0] * len(ids)
    return list(zip(ids, [1.0 - d for d in distances]))  # distance → similarity
