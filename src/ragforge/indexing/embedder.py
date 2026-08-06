"""Embedding with fingerprint-based cache to avoid re-embedding."""

from ..pipeline import Chunk
from ragforge.cache.embedding_cache import EmbeddingCache


def embed_chunks(chunks: list[Chunk], cache: EmbeddingCache, tenant_id: str = "default") -> list[Chunk]:
    """Generate embeddings for chunks, skipping cached ones.

    Uses sentence-transformers for local embeddings by default.
    Falls back to configured remote provider (SiliconFlow, OpenAI-compatible).
    """
    from ragforge.config import get_config

    cfg = get_config()
    provider = cfg.embedding_provider  # "local" | "siliconflow" | "openai"

    uncached = []
    for c in chunks:
        if not cache.has(c["id"]):
            uncached.append(c)

    if uncached:
        texts = [c["content"] for c in uncached]
        if provider == "local":
            vectors = _embed_local(texts)
        else:
            vectors = _embed_remote(texts, provider)

        for c, vec in zip(uncached, vectors):
            cache.set(c["id"], vec, tenant_id=tenant_id)

    return chunks


def get_embedding(text: str) -> list[float]:
    """Get embedding for a single text (for query-time use)."""
    from ragforge.config import get_config
    cfg = get_config()
    if cfg.embedding_provider == "local":
        return _embed_local([text])[0]
    return _embed_remote([text], cfg.embedding_provider)[0]


# ── Providers ───────────────────────────────────────────────────

_model = None

def _get_local_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    return _model

def _embed_local(texts: list[str]) -> list[list[float]]:
    model = _get_local_model()
    return model.encode(texts, normalize_embeddings=True).tolist()


def _embed_remote(texts: list[str], provider: str) -> list[list[float]]:
    """Use OpenAI-compatible embedding API."""
    import httpx
    from ragforge.config import get_config

    cfg = get_config()
    url = cfg.embedding_endpoint
    api_key = cfg.embedding_api_key
    model = cfg.embedding_model

    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": texts, "model": model},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]
