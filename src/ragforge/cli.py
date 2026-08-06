"""RAG Forge CLI — ragforge ingest/ask/serve."""

import click
from pathlib import Path


@click.group()
@click.version_option(version="0.1.0")
def main():
    """RAG Forge — Enterprise RAG pipeline."""
    pass


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--tenant", "-t", default="default", help="Tenant ID for multi-tenant isolation")
@click.option("--strategy", "-s", default="paragraph", help="Chunking strategy: paragraph | markdown")
def ingest(paths: tuple[str], tenant: str, strategy: str):
    """Ingest documents into the knowledge base."""
    from ragforge.ingestion.parser import parse_file
    from ragforge.ingestion.chunker import chunk_documents
    from ragforge.pipeline import Document

    click.echo(f"Ingesting {len(paths)} file(s) into tenant '{tenant}' (strategy={strategy})...")

    documents = []
    for p in paths:
        doc = parse_file(Path(p), tenant_id=tenant)
        documents.append(doc)
        click.echo(f"  parsed: {doc['metadata']['filename']} ({doc['metadata']['char_count']} chars)")

    # Chunk with selected strategy, then index
    from ragforge.pipeline import run_indexing as _run_indexing
    # Override default chunker strategy by chunking here
    chunks = chunk_documents(documents, strategy=strategy)
    # Embed + index via pipeline
    from ragforge.indexing.embedder import embed_chunks
    from ragforge.indexing.vector_store import index_chunks
    from ragforge.cache.embedding_cache import EmbeddingCache
    cache = EmbeddingCache()
    chunks = embed_chunks(chunks, cache=cache, tenant_id=tenant)
    index_chunks(chunks, tenant_id=tenant)
    click.echo(f"Done: {len(chunks)} chunks indexed.")


@main.command()
@click.argument("question")
@click.option("--tenant", "-t", default="default", help="Tenant ID")
def ask(question: str, tenant: str):
    """Ask a question against the knowledge base."""
    from ragforge.pipeline import run_query

    click.echo(f"Querying tenant '{tenant}': {question}")
    state = run_query(question, tenant_id=tenant)

    if state.get("errors"):
        click.echo(f"Errors: {state['errors']}", err=True)
        return

    click.echo(f"\n{state['answer']}\n")
    if state.get("citations"):
        click.echo("Sources:")
        for c in state["citations"]:
            click.echo(f"  - {c['snippet']}")

    if state.get("evaluation"):
        click.echo(f"\nQuality: {state['evaluation']}")


@main.command()
@click.option("--host", default="127.0.0.1", help="Bind address")
@click.option("--port", default=8777, help="Port")
def serve(host: str, port: int):
    """Start the RAG Forge API server."""
    import uvicorn
    click.echo(f"Starting RAG Forge API on http://{host}:{port}")
    uvicorn.run("ragforge.api.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
