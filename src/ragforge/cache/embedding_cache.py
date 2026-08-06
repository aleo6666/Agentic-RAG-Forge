"""Embedding cache with document fingerprinting.

Design decision:
  - Fingerprint = md5(doc_content) — deterministic, no false positives.
  - Cache stores (doc_id, tenant_id) → embedding vector.
  - On re-ingest: fingerprint match → skip embedding → reuse cached vector.

This is NOT RAG semantic similarity. It's deterministic deduplication —
if the same exact content is ingested twice, we don't re-embed.
"""

from hashlib import md5
import json
from pathlib import Path


class EmbeddingCache:
    """Simple JSON-file-backed embedding cache.

    ponytail: JSON file, not SQLite — < 10K entries, O(n) scan is fine.
    Upgrade to SQLite if entries exceed 50K.
    """

    def __init__(self, cache_dir: str = "./cache"):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "embedding_cache.json"
        self._data: dict[str, list[float]] = self._load()

    def _load(self) -> dict:
        try:
            if self._file.exists():
                return json.loads(self._file.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache — start fresh
        return {}

    def _save(self) -> None:
        # Atomic write: tmp → rename prevents corruption on crash
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data))
        tmp.replace(self._file)

    def _key(self, chunk_id: str, tenant_id: str) -> str:
        return f"{tenant_id}:{chunk_id}"

    def has(self, chunk_id: str, tenant_id: str = "default") -> bool:
        return self._key(chunk_id, tenant_id) in self._data

    def get(self, chunk_id: str, tenant_id: str = "default") -> list[float] | None:
        return self._data.get(self._key(chunk_id, tenant_id))

    def set(self, chunk_id: str, vector: list[float], tenant_id: str = "default") -> None:
        self._data[self._key(chunk_id, tenant_id)] = vector
        # ponytail: save on every set — small data, infrequent writes.
        # Batch-save if write frequency becomes a bottleneck.
        self._save()

    def stats(self) -> dict:
        """Return cache stats: total entries, size on disk."""
        return {
            "entries": len(self._data),
            "size_bytes": self._file.stat().st_size if self._file.exists() else 0,
        }


def fingerprint(content: str) -> str:
    """Compute a deterministic fingerprint for a piece of content."""
    return md5(content.encode()).hexdigest()[:16]
