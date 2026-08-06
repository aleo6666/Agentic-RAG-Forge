"""Quick verification: all modules import cleanly and core pipeline compiles."""
import sys
sys.path.insert(0, "src")

def test_imports():
    """All modules import without error."""
    modules = [
        "ragforge.pipeline",
        "ragforge.ingestion.parser",
        "ragforge.ingestion.chunker",
        "ragforge.indexing.embedder",
        "ragforge.indexing.vector_store",
        "ragforge.cache.embedding_cache",
    ]
    for mod in modules:
        __import__(mod)
        print(f"  OK  {mod}")

def test_cache():
    """Embedding cache works."""
    from ragforge.cache.embedding_cache import EmbeddingCache, fingerprint
    import tempfile, os

    cache = EmbeddingCache(cache_dir="cache_test")
    assert not cache.has("chunk1")
    cache.set("chunk1", [0.1, 0.2, 0.3])
    assert cache.has("chunk1")
    assert cache.get("chunk1") == [0.1, 0.2, 0.3]

    fp = fingerprint("hello world")
    assert len(fp) == 16
    assert fingerprint("hello world") == fp  # deterministic

    # cleanup
    os.remove("cache_test/embedding_cache.json")
    os.rmdir("cache_test")
    print("  OK  embedding cache")

def test_parser():
    """Parser handles various inputs."""
    from ragforge.pipeline import Document

    docs = [
        {"id": "d1", "content": "Hello world\n\nThis is a test.", "metadata": {}},
        {"id": "d2", "content": "", "metadata": {}},
    ]
    from ragforge.ingestion.parser import parse_documents
    result = parse_documents(docs)
    assert result[0]["metadata"]["char_count"] == 28
    assert result[1]["metadata"]["char_count"] == 0
    print("  OK  parser")

def test_chunker():
    """Chunker produces non-empty chunks."""
    from ragforge.pipeline import Document
    from ragforge.ingestion.chunker import chunk_documents

    docs = [{
        "id": "d1", "content": "段落一\n\n段落二\n\n段落三" * 50,
        "metadata": {"filename": "test.md"},
    }]
    chunks = chunk_documents(docs, strategy="paragraph", max_chars=500)
    assert len(chunks) > 1, f"Expected multiple chunks, got {len(chunks)}"
    assert all(len(c["content"]) > 0 for c in chunks)
    assert chunks[0]["doc_id"] == "d1"
    print(f"  OK  chunker ({len(chunks)} chunks)")

def test_pipeline_graph():
    """LangGraph pipeline compiles."""
    try:
        from ragforge.pipeline import build_rag_pipeline
        graph = build_rag_pipeline()
        compiled = graph.compile()
        assert compiled is not None
        print("  OK  pipeline graph compiled")
    except ImportError:
        print("  SKIP pipeline graph (langgraph not installed — run: pip install langgraph)")

def test_fingerprint_dedup():
    """Same content → same fingerprint → cache hit."""
    from ragforge.cache.embedding_cache import fingerprint

    a = fingerprint("The quick brown fox jumps over the lazy dog.")
    b = fingerprint("The quick brown fox jumps over the lazy dog.")
    c = fingerprint("Different content here.")
    assert a == b, "Same content must have same fingerprint"
    assert a != c, "Different content must have different fingerprint"
    print("  OK  fingerprint dedup")


if __name__ == "__main__":
    print("=== RagForge Verification ===\n")
    test_imports()
    test_cache()
    test_parser()
    test_chunker()
    test_pipeline_graph()
    test_fingerprint_dedup()
    print("\n=== All checks passed ===")
