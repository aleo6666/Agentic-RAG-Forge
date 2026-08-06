"""Document ingestion: parse PDF, Markdown, TXT into Document dicts."""

from pathlib import Path
from hashlib import md5
from ..pipeline import Document


SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt", ".markdown"}


def parse_file(filepath: Path, tenant_id: str = "default") -> Document:
    """Parse a single file into a Document."""
    suffix = filepath.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported format: {suffix}")

    if suffix == ".pdf":
        content = _parse_pdf(filepath)
    else:
        content = filepath.read_text(encoding="utf-8", errors="replace")

    doc_id = md5(str(filepath).encode()).hexdigest()[:12]
    return {
        "id": doc_id,
        "content": content,
        "metadata": {
            "filename": filepath.name,
            "mime_type": suffix,
            "tenant_id": tenant_id,
            "char_count": len(content),
        },
    }


def parse_documents(documents: list[Document]) -> list[Document]:
    """Parse pre-loaded documents (for API uploads). Already have content, just enrich metadata."""
    for doc in documents:
        if "char_count" not in doc.get("metadata", {}):
            doc.setdefault("metadata", {})["char_count"] = len(doc.get("content", ""))
    return documents


def _parse_pdf(filepath: Path) -> str:
    """Extract text from PDF using pymupdf. Lightweight, no OCR."""
    import pymupdf
    doc = pymupdf.open(str(filepath))
    parts = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            parts.append(text)
    doc.close()
    return "\n\n".join(parts)
