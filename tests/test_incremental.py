"""DocumentHash incremental indexing tests — real Chroma in a temp dir.

Verifies: first-index, idempotent re-index (skip), content change
(remove old + add new), and cleanup.
"""

import sys, os
sys.path.insert(0, "src")
os.environ["DEEPSEEK_API_KEY"] = "sk-test"


def _mk(content: str, doc_id: str = "d1", i: int = 0) -> dict:
    return {
        "id": f"{doc_id}_{i}",
        "content": content,
        "doc_id": doc_id,
        "metadata": {"filename": f"{doc_id}.md", "_embedding": [0.1] * 8},
    }


def test_incremental_dedup_and_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from ragforge.indexing.vector_store import index_chunks, list_documents, clear_documents, _collections
    _collections.clear()
    try:
        # 1) First index
        r1 = index_chunks([_mk("内容A", i=0), _mk("内容B", i=1)])
        assert r1 == {"added": 2, "skipped": 0, "removed": 0}, r1

        # 2) Re-index identical content → all skipped (idempotent)
        r2 = index_chunks([_mk("内容A", i=0), _mk("内容B", i=1)])
        assert r2 == {"added": 0, "skipped": 2, "removed": 0}, r2

        # 3) B changed to C → A skipped, B removed, C added
        r3 = index_chunks([_mk("内容A", i=0), _mk("内容C", i=1)])
        assert r3["added"] == 1 and r3["skipped"] == 1 and r3["removed"] == 1, r3

        # 4) Store now holds exactly A + C
        docs = list_documents("default")
        assert len(docs) == 1 and docs[0]["chunks"] == 2, docs

        # 5) Document deleted explicitly → all its chunks purged
        from ragforge.indexing.vector_store import remove_document
        removed = remove_document("d1", "default")
        assert removed == 2, removed
        r4 = index_chunks([_mk("新文档内容", doc_id="d2", i=0)])
        assert r4["added"] == 1
        docs = {d["filename"]: d["chunks"] for d in list_documents("default")}
        assert docs == {"d2.md": 1}, docs  # d1 的 chunks 已被清掉

        # 6) Cleanup
        removed = clear_documents("default")
        assert removed == 1
    finally:
        _collections.clear()
