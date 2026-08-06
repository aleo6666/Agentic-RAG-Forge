"""RAG evaluation using RAGAS metrics."""


def evaluate_generation(question: str, answer: str, contexts: list[str]) -> dict:
    """Evaluate answer quality against contexts.

    Returns a dict of metrics. RAGAS is imported lazily.
    """
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision
        from datasets import Dataset

        ds = Dataset.from_dict({
            "question": [question],
            "answer": [answer],
            "contexts": [contexts],
        })

        result = evaluate(ds, metrics=[faithfulness, answer_relevancy, context_precision])
        return {k: round(float(v), 4) for k, v in result.items()}
    except ImportError:
        # No RAGAS installed — return placeholder
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
            "note": "RAGAS not installed. Run: pip install ragas",
        }
