import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from yuxi.knowledge.eval.metrics import EvaluationMetricsCalculator, RetrievalMetrics


def test_retrieval_metrics_use_metadata_chunk_id():
    retrieved_chunks = [
        {"metadata": {"chunk_id": "chunk_a"}},
        {"metadata": {"chunk_id": "chunk_b"}},
    ]

    metrics = EvaluationMetricsCalculator.calculate_retrieval_metrics(
        retrieved_chunks, ["chunk_b", "chunk_c"], k_values=[1, 3]
    )

    assert metrics["recall@1"] == 0.0
    assert metrics["recall@3"] == 0.5
    assert metrics["f1@3"] == RetrievalMetrics.f1_score_at_k(["chunk_a", "chunk_b"], ["chunk_b", "chunk_c"], 3)


def test_overall_score_keeps_existing_average_strategy():
    score = EvaluationMetricsCalculator.calculate_overall_score(
        [{"recall@1": 1.0, "f1@1": 0.5}], [{"score": 0.25}]
    )

    assert score == 0.5
