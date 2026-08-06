"""RAG Forge — Enterprise RAG pipeline builder.

Pipeline stages:
  INGEST → CHUNK → EMBED → INDEX → RETRIEVE → RERANK → GENERATE → (EVALUATE)

Each stage is a LangGraph node — independently swappable, testable, and traceable.
"""

from typing import TypedDict, Literal

# ponytail: lazy import — langgraph is heavy, only needed when building the graph
def _get_graph():
    from langgraph.graph import StateGraph, END
    return StateGraph, END


# ── Pipeline State ──────────────────────────────────────────────

class Document(TypedDict):
    """A single document in the pipeline."""
    id: str
    content: str
    metadata: dict  # filename, mime_type, tenant_id, etc.


class Chunk(TypedDict):
    """A chunk produced by the chunker."""
    id: str
    content: str
    doc_id: str
    metadata: dict


class RetrievedChunk(TypedDict):
    """A retrieved chunk with relevance score."""
    chunk: Chunk
    score: float
    source: str  # "dense" | "sparse" | "hybrid"


class PipelineState(TypedDict):
    """State flowing through the RAG pipeline."""
    # Input
    documents: list[Document]
    query: str
    tenant_id: str

    # Intermediate
    chunks: list[Chunk]
    retrieved: list[RetrievedChunk]
    reranked: list[RetrievedChunk]
    context: str

    # Output
    answer: str
    citations: list[dict]
    evaluation: dict

    # Control
    errors: list[str]


# ── Pipeline Nodes ──────────────────────────────────────────────

def ingest(state: PipelineState) -> PipelineState:
    """Parse raw documents into text content."""
    from ragforge.ingestion.parser import parse_documents
    parsed = parse_documents(state["documents"])
    return {**state, "documents": parsed, "errors": []}


def chunk(state: PipelineState) -> PipelineState:
    """Split documents into semantic chunks."""
    from ragforge.ingestion.chunker import chunk_documents
    chunks = chunk_documents(state["documents"])
    return {**state, "chunks": chunks}


def embed(state: PipelineState) -> PipelineState:
    """Generate embeddings for chunks (with fingerprint cache)."""
    from ragforge.indexing.embedder import embed_chunks
    from ragforge.cache.embedding_cache import EmbeddingCache

    cache = EmbeddingCache()
    chunks = embed_chunks(state["chunks"], cache=cache, tenant_id=state["tenant_id"])
    return {**state, "chunks": chunks}


def index(state: PipelineState) -> PipelineState:
    """Index chunks into vector store."""
    from ragforge.indexing.vector_store import index_chunks
    index_chunks(state["chunks"], tenant_id=state["tenant_id"])
    return state


def retrieve(state: PipelineState) -> PipelineState:
    """Hybrid retrieval: dense + sparse → RRF fusion."""
    from ragforge.retrieval.hybrid import hybrid_retrieve
    results = hybrid_retrieve(state["query"], tenant_id=state["tenant_id"], top_k=20)
    return {**state, "retrieved": results}


def rerank(state: PipelineState) -> PipelineState:
    """Rerank retrieved chunks for precision."""
    from ragforge.retrieval.reranker import rerank_chunks
    reranked = rerank_chunks(state["query"], state["retrieved"], top_k=5)
    return {**state, "reranked": reranked}


def generate(state: PipelineState) -> PipelineState:
    """Generate answer with citations from reranked context."""
    from ragforge.generation.generator import generate_answer
    context_parts = [r["chunk"]["content"] for r in state["reranked"]]
    context = "\n\n---\n\n".join(context_parts)
    answer, citations = generate_answer(state["query"], context)
    return {**state, "context": context, "answer": answer, "citations": citations}


def evaluate(state: PipelineState) -> PipelineState:
    """Evaluate generation quality (RAGAS)."""
    from ragforge.evaluation.evaluator import evaluate_generation
    if state["answer"] and state["context"]:
        return {**state, "evaluation": evaluate_generation(
            question=state["query"],
            answer=state["answer"],
            contexts=[r["chunk"]["content"] for r in state["reranked"]],
        )}
    return state


# ── Graph Builder ────────────────────────────────────────────────

def build_rag_pipeline():
    """Build the LangGraph RAG pipeline.

    Two execution modes:
      - indexing: ingest → chunk → embed → index → END
      - query:    retrieve → rerank → generate → evaluate → END

    Nodes are pure functions (no side effects beyond state mutation),
    making them independently testable.
    """
    StateGraph, END = _get_graph()
    graph = StateGraph(PipelineState)

    graph.add_node("ingest", ingest)
    graph.add_node("chunk", chunk)
    graph.add_node("embed", embed)
    graph.add_node("index", index)
    graph.add_node("retrieve", retrieve)
    graph.add_node("rerank", rerank)
    graph.add_node("generate", generate)
    graph.add_node("evaluate", evaluate)

    # Conditional routing: indexing vs query
    def route(state: PipelineState) -> Literal["ingest", "retrieve"]:
        if state.get("documents") and not state.get("query"):
            return "ingest"
        return "retrieve"

    graph.set_conditional_entry_point(
        route,
        {"ingest": "ingest", "retrieve": "retrieve"},
    )

    # Indexing path
    graph.add_edge("ingest", "chunk")
    graph.add_edge("chunk", "embed")
    graph.add_edge("embed", "index")
    graph.add_edge("index", END)

    # Query path
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", "evaluate")
    graph.add_edge("evaluate", END)

    return graph


# ── Convenience ─────────────────────────────────────────────────

_rag_pipeline = None

def get_pipeline():
    """Get or build the compiled LangGraph pipeline (lazy init)."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = build_rag_pipeline().compile()
    return _rag_pipeline


def run_indexing(documents: list[Document], tenant_id: str = "default") -> PipelineState:
    """Run the indexing pipeline synchronously."""
    return get_pipeline().invoke({"documents": documents, "tenant_id": tenant_id, "query": ""})


def run_query(query: str, tenant_id: str = "default") -> PipelineState:
    """Run the query pipeline synchronously."""
    return get_pipeline().invoke({"query": query, "tenant_id": tenant_id, "documents": []})
