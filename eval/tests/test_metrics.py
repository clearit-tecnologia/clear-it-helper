import math

import pytest

from ch_eval.metrics import (
    chunk_coverage,
    hit_at_k,
    mean,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
    retrieval_scores,
)

E = frozenset()


def cov(*sets):
    return [frozenset(s) for s in sets]


def test_recall_single_evidence():
    c = cov((), (), (0,), ())
    assert recall_at_k(c, 1, 1) == 0.0
    assert recall_at_k(c, 1, 3) == 1.0
    assert recall_at_k(c, 1, 10) == 1.0


def test_recall_multi_hop_partial_and_duplicates():
    # chunk 1 and 2 both cover evidence 0 (overlap); evidence 1 only at rank 4
    c = cov((0,), (0,), (), (1,))
    assert recall_at_k(c, 2, 1) == 0.5
    assert recall_at_k(c, 2, 3) == 0.5
    assert recall_at_k(c, 2, 5) == 1.0


def test_recall_requires_evidence():
    with pytest.raises(ValueError, match="evidence"):
        recall_at_k(cov((0,)), 0, 1)


def test_mrr_known_cases():
    assert reciprocal_rank(cov((0,), ())) == 1.0
    assert reciprocal_rank(cov((), (), (0,))) == pytest.approx(1 / 3)
    assert reciprocal_rank(cov((), ())) == 0.0
    assert reciprocal_rank([]) == 0.0


def test_hit_at_k():
    c = cov((), (1,))
    assert hit_at_k(c, 1) == 0.0
    assert hit_at_k(c, 3) == 1.0


def test_ndcg_perfect_and_rank_two():
    assert ndcg_at_k(cov((0,), ()), 1, 10) == pytest.approx(1.0)
    # single relevant at rank 2 -> 1/log2(3)
    assert ndcg_at_k(cov((), (0,)), 1, 10) == pytest.approx(1 / math.log2(3))
    assert ndcg_at_k(cov((), (0,)), 1, 1) == 0.0


def test_ndcg_duplicates_do_not_inflate():
    # two chunks with the same quote: second gives no gain; ideal has two new items
    c = cov((0,), (0,), (1,))
    expected = (1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert ndcg_at_k(c, 2, 10) == pytest.approx(expected)
    # one chunk covering both evidence items at rank 1
    assert ndcg_at_k(cov((0, 1)), 2, 10) == pytest.approx(1 / (1 + 1 / math.log2(3)))


def test_ndcg_bounded():
    c = cov((0, 1), (1,), (0,), (2,))
    for k in (1, 3, 5, 10):
        assert 0.0 <= ndcg_at_k(c, 3, k) <= 1.0


def test_retrieval_scores_keys():
    s = retrieval_scores(cov((), (0,)), 1)
    assert s["mrr"] == 0.5
    assert s["recall@1"] == 0.0
    assert s["recall@3"] == 1.0
    assert set(s) == {"mrr"} | {
        f"{m}@{k}" for m in ("recall", "hit", "ndcg") for k in (1, 3, 5, 10)
    }


def test_chunk_coverage_uses_normalized_quote_and_document():
    evidence = [
        {"document": "a.txt", "quote": "Prazo de  20 (vinte)\nDIAS", "locator": "x"},
        {"document": "b.txt", "quote": "outra lei", "locator": "y"},
    ]
    results = [
        {"filename": "a.txt", "text": "... o prazo de 20 (vinte) dias, prorrogável ..."},
        {"filename": "a.txt", "text": "menciona outra lei, mas no documento errado"},
        {"filename": "b.txt", "text": "Outra   Lei aqui"},
        {"text": "sem filename: prazo de 20 (vinte) dias"},
    ]
    assert chunk_coverage(results, evidence) == [E | {0}, E, E | {1}, E | {0}]


def test_percentile_linear_interpolation():
    data = [100, 200, 300, 400, 500]
    assert percentile(data, 50) == 300
    assert percentile(data, 95) == pytest.approx(480)
    assert percentile([42], 95) == 42
    assert percentile([], 50) is None


def test_mean_ignores_none_and_nan():
    assert mean([1.0, None, float("nan"), 3.0]) == 2.0
    assert mean([None]) is None
