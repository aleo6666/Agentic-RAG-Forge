"""Semantic chunking with configurable strategy."""

import re
from hashlib import md5
from ..pipeline import Document, Chunk


# ── Chunking Strategies ─────────────────────────────────────────

def chunk_by_paragraph(text: str, max_chars: int = 1000, overlap: int = 100) -> list[str]:
    """Split by double-newline, merge short paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        if current and len(current) + len(para) > max_chars:
            chunks.append(current)
            # ponytail: overlap = last 100 chars of previous chunk
            current = current[-overlap:] + "\n\n" + para if overlap else para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip():
        chunks.append(current)

    return chunks


def chunk_by_markdown_headers(text: str, max_chars: int = 1500) -> list[str]:
    """Split at markdown headers (#, ##, ###), keep sections together."""
    sections = re.split(r"\n(?=#{1,3}\s)", text)
    return [s.strip() for s in sections if s.strip() and len(s.strip()) > 20]


# ── Main Chunker ────────────────────────────────────────────────

def chunk_documents(
    documents: list[Document],
    strategy: str = "paragraph",
    max_chars: int = 1000,
    overlap: int = 100,
) -> list[Chunk]:
    """Chunk all documents using the specified strategy.

    Strategies:
      - paragraph: split by double-newline (default, works for most formats)
      - markdown:  split at ## headers (best for markdown docs)
    """
    chunkers = {"paragraph": chunk_by_paragraph, "markdown": chunk_by_markdown_headers}
    if strategy not in chunkers:
        raise ValueError(f"Unknown chunking strategy: {strategy!r}. Options: {list(chunkers)}")
    chunker = chunkers[strategy]

    all_chunks = []
    for doc in documents:
        text = doc["content"]
        if not text.strip():
            continue

        parts = chunker(text, max_chars=max_chars)
        for i, part in enumerate(parts):
            chunk_id = md5(f"{doc['id']}_{i}".encode()).hexdigest()[:12]
            all_chunks.append({
                "id": chunk_id,
                "content": part,
                "doc_id": doc["id"],
                "metadata": {
                    **doc.get("metadata", {}),
                    "chunk_index": i,
                    "strategy": strategy,
                },
            })

    return all_chunks
