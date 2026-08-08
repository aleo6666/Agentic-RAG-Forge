"""RAG Forge CLI — ragforge ingest/ask/agent-ask/eval-compare/serve."""

import click
import json
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
@click.argument("question")
@click.option("--tenant", "-t", default="default", help="Tenant ID")
@click.option("--max-rounds", default=3, show_default=True, help="Max retrieval rounds")
@click.option("--trace/--no-trace", default=True, help="Show agent decision trace")
def agent_ask(question: str, tenant: str, max_rounds: int, trace: bool):
    """Ask with Agentic RAG — routing, grading, query rewriting loops."""
    from ragforge.agentic.agentic_pipeline import run_agentic_query

    click.echo(f"Agent querying tenant '{tenant}': {question}")
    state = run_agentic_query(question, tenant_id=tenant, max_rounds=max_rounds)

    if trace and state.get("trace"):
        click.echo("\n── Agent trace ──")
        for t in state["trace"]:
            step = t.get("step")
            if step == "route":
                click.echo(f"  route       → {t.get('decision')}  ({t.get('reason', '')})")
            elif step == "retrieve":
                click.echo(f"  retrieve    → {t.get('hits')} hits  (query: {t.get('query', '')[:60]})")
            elif step == "grade_docs":
                click.echo(f"  grade_docs  → {t.get('relevant')}/{t.get('total')} relevant")
            elif step == "rewrite":
                click.echo(f"  rewrite     → {t.get('rewritten', '')[:60]}  ({t.get('reason', '')[:40]})")
            elif step == "generate":
                click.echo(f"  generate    → {t.get('context_chunks')} context chunks")
            elif step == "grade_answer":
                click.echo(f"  grade_answer→ grounded={t.get('grounded')}  ({t.get('reason', '')[:50]})")
            elif step == "direct":
                click.echo("  direct      → answered without retrieval")
            elif step == "clarify":
                click.echo("  clarify     → asked for clarification")

    click.echo(f"\n{state['answer']}\n")
    if state.get("citations"):
        click.echo("Sources:")
        for c in state["citations"]:
            click.echo(f"  - {c['snippet']}")


@main.command()
@click.argument("questions_file", type=click.Path(exists=True))
@click.option("--tenant", "-t", default="default", help="Tenant ID")
@click.option("--max-rounds", default=3, show_default=True, help="Max agentic retrieval rounds")
def eval_compare(questions_file: str, tenant: str, max_rounds: int):
    """Compare deterministic vs Agentic RAG with an LLM judge.

    QUESTIONS_FILE: JSONL, one {"question": "...", "note": "..."} per line.
    """
    from ragforge.evaluation.compare import run_comparison, format_report
    from rich.console import Console
    from rich.markdown import Markdown

    questions = []
    with open(questions_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))

    click.echo(f"Evaluating {len(questions)} questions (tenant '{tenant}', max_rounds={max_rounds})...")
    results = run_comparison(questions, tenant_id=tenant, max_rounds=max_rounds)

    report = format_report(results)
    Console().print(Markdown(report))
    out_path = Path(questions_file).with_suffix(".report.md")
    out_path.write_text(report, encoding="utf-8")
    click.echo(f"\nReport saved: {out_path}")


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
