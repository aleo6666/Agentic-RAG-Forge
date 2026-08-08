"""Hybrid retrieval 单测：中文分词 / 空文档 / metadatas=None / RRF 融合"""
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, "src")

from ragforge.retrieval.hybrid import tokenize, hybrid_retrieve, search_sparse, _rrf_fuse


def test_tokenize_mixed():
    """中英混合分词。"""
    t = tokenize("如何部署RAG系统到ECS")
    assert "rag" in t, f"英文单词缺失: {t}"
    assert "如" in t and "何" in t, f"中文字符缺失: {t}"
    assert len(t) == 9, f"分词数量不符: {t}"
    print(f"  OK  tokenize mixed: {t}")


def test_tokenize_empty():
    assert tokenize("") == []
    assert tokenize(None) == []
    print("  OK  tokenize empty")


def _fake_collection(docs, ids=None, metadatas=None):
    """构造伪 Chroma collection。"""
    return MagicMock(
        get=MagicMock(return_value={
            "ids": ids or [f"c{i}" for i in range(len(docs))],
            "documents": docs,
            "metadatas": metadatas,
        })
    )


def test_sparse_chinese_query():
    """中文查询命中中文文档（回归：旧版 query.split() 整句一刀切）。"""
    docs = [
        "部署RAG系统到阿里云ECS服务器",
        "Docker Compose 部署微服务集群",
        "How to deploy RAG system on cloud",
        "MySQL 索引优化与慢查询分析",
    ]
    collection = _fake_collection(docs)
    with patch("ragforge.indexing.vector_store._get_collection", return_value=collection):
        results = search_sparse("如何部署RAG系统", "default", top_k=2)
    assert len(results) == 2, f"期望 2 条，实际 {len(results)}"
    top = results[0]["chunk"]["content"]
    assert "部署" in top or "RAG" in top, f"中文检索未命中相关文档: {top}"
    print(f"  OK  sparse chinese query → {top[:30]}")


def test_sparse_empty_docs():
    """全空文档不崩（回归：旧版 BM25 对空 token 抛异常）。"""
    collection = _fake_collection(["", "", "   "])
    with patch("ragforge.indexing.vector_store._get_collection", return_value=collection):
        results = search_sparse("测试", "default")
    assert results == [], f"期望空结果，实际 {results}"
    print("  OK  sparse empty docs → []")


def test_sparse_metadatas_none():
    """metadatas=None 不崩（回归：旧版 None.get 抛 TypeError）。"""
    collection = _fake_collection(["文档一内容", "文档二内容"], metadatas=None)
    with patch("ragforge.indexing.vector_store._get_collection", return_value=collection):
        results = search_sparse("文档", "default", top_k=5)
    assert len(results) == 2, f"期望 2 条，实际 {len(results)}"
    assert all(r["chunk"]["doc_id"] == "" for r in results)
    print("  OK  sparse metadatas=None safe")


def test_sparse_empty_query():
    """空查询返回 []。"""
    collection = _fake_collection(["内容"])
    with patch("ragforge.indexing.vector_store._get_collection", return_value=collection):
        assert search_sparse("", "default") == []
        assert search_sparse("   ", "default") == []
    print("  OK  sparse empty query → []")


def test_dense_metadatas_none():
    """dense 分支 metadatas=None 不崩。"""
    dense_raw = [("c0", 0.9), ("c1", 0.8)]
    collection = _fake_collection(["内容A", "内容B"], ids=["c0", "c1"], metadatas=None)
    with patch("ragforge.indexing.vector_store.search_dense", return_value=dense_raw), \
         patch("ragforge.indexing.vector_store._get_collection", return_value=collection):
        results = hybrid_retrieve("查询", "default", top_k=2)
    assert len(results) == 2
    print("  OK  dense metadatas=None safe")


def test_rrf_fuse():
    """RRF 融合：跨 dense/sparse 排名合并。"""
    dense = [
        {"chunk": {"id": "a"}, "score": 1.0, "source": "dense"},
        {"chunk": {"id": "b"}, "score": 0.9, "source": "dense"},
    ]
    sparse = [
        {"chunk": {"id": "b"}, "score": 1.0, "source": "sparse"},
        {"chunk": {"id": "c"}, "score": 0.8, "source": "sparse"},
    ]
    fused = _rrf_fuse(dense, sparse, k=60)
    ids = [f["chunk"]["id"] for f in fused]
    assert ids[0] == "b", f"双路命中的 b 应排第一: {ids}"
    assert set(ids) == {"a", "b", "c"}
    print(f"  OK  RRF fuse → {ids}")


if __name__ == "__main__":
    print("=== Hybrid Retrieval Tests ===\n")
    test_tokenize_mixed()
    test_tokenize_empty()
    test_sparse_chinese_query()
    test_sparse_empty_docs()
    test_sparse_metadatas_none()
    test_sparse_empty_query()
    test_dense_metadatas_none()
    test_rrf_fuse()
    print("\n=== All hybrid tests passed ===")
