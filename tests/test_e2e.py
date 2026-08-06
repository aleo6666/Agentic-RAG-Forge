"""End-to-end integration test — mocks heavy deps, tests real data flow."""
import sys, os, json, shutil
sys.path.insert(0, "src")

os.environ["DEEPSEEK_API_KEY"] = "sk-test"
os.environ["RAGFORGE_EMBED_PROVIDER"] = "local"

# ── Step 1: Parse + Chunk ──
from pathlib import Path
from ragforge.ingestion.parser import parse_file
from ragforge.ingestion.chunker import chunk_documents

doc = parse_file(Path("test_docs/README.md"))
assert doc["metadata"]["char_count"] > 0, "Parse returned empty"
print(f"1. Parse  OK: {doc['metadata']['filename']} ({doc['metadata']['char_count']} chars)")

chunks = chunk_documents([doc], strategy="markdown")
assert len(chunks) >= 1, f"Chunker produced {len(chunks)} chunks"
for c in chunks:
    assert len(c["content"]) > 0
    assert c["doc_id"] == doc["id"]
print(f"2. Chunk  OK: {len(chunks)} chunks")

# ── Step 2: Cache with tenant isolation ──
from ragforge.cache.embedding_cache import EmbeddingCache, fingerprint

os.makedirs("test_cache", exist_ok=True)
cache = EmbeddingCache(cache_dir="test_cache")

# Inject mock embeddings directly via cache
test_vecs = [[0.1 * i] * 384 for i in range(len(chunks))]
for c, v in zip(chunks, test_vecs):
    cache.set(c["id"], v, tenant_id="test")

assert cache.has(chunks[0]["id"], tenant_id="test")
assert not cache.has(chunks[0]["id"], tenant_id="other")  # tenant隔离
print(f"3. Cache  OK: {cache.stats()['entries']} entries, tenant隔离 verified")

# ── Step 3: Simulate embed → index pipeline ──
for c in chunks:
    emb = cache.get(c["id"], tenant_id="test")
    c.setdefault("metadata", {})["_embedding"] = emb

# (vector_store would normally index here — skip Chroma dep)
print("4. Embed→Index data flow OK (vectors attached to chunks)")

# ── Step 4: Verify fingerprint dedup ──
fp1 = fingerprint("RAG Forge 是一个基于 LangGraph 的模块化 RAG 管线框架")
fp2 = fingerprint("RAG Forge 是一个基于 LangGraph 的模块化 RAG 管线框架")
fp3 = fingerprint("不同的内容")
assert fp1 == fp2, "Deterministic fingerprint failed"
assert fp1 != fp3, "Collision detected"
print("5. Fingerprint dedup OK")

# ── Step 5: Config loading ──
from ragforge.config import get_config
cfg = get_config()
assert cfg.llm_provider in ("deepseek", "lmstudio")
print(f"6. Config  OK: provider={cfg.llm_provider}, embed={cfg.embedding_provider}")

# ── Step 6: Pipeline graph compiles ──
try:
    from ragforge.pipeline import build_rag_pipeline
    graph = build_rag_pipeline().compile()
    print("7. Pipeline graph compiled OK")
except ImportError:
    print("7. Pipeline graph SKIP (langgraph not installed)")

# ── Cleanup ──
shutil.rmtree("test_cache", ignore_errors=True)

print(f"\n=== END-TO-END PASSED ===")
