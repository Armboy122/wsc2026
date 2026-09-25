"""BM25, rank and RRF fusion math tests."""

from __future__ import annotations

import numpy as np

from app.knowledge.index import (
    RRF_K,
    Bm25Ranker,
    order_by_score,
    ranks_from_scores,
    rrf,
)


def test_ranks_from_scores_is_descending_and_stable_for_ties() -> None:
    ranks = ranks_from_scores(np.array([0.5, 2.0, 2.0, -1.0]))
    assert list(ranks) == [2, 0, 1, 3]


def test_order_by_score_is_stable_for_ties() -> None:
    assert list(order_by_score(np.array([1.0, 3.0, 3.0, 0.0]))) == [1, 2, 0, 3]
    assert order_by_score(np.array([])).size == 0


def test_rrf_matches_the_reciprocal_rank_formula() -> None:
    bm25_ranks = np.array([0, 1, 2])
    dense_ranks = np.array([2, 0, 1])
    fused = rrf([bm25_ranks, dense_ranks], k=60)

    assert fused[0] == 1 / 60 + 1 / 62
    assert fused[1] == 1 / 61 + 1 / 60
    assert fused[2] == 1 / 62 + 1 / 61
    assert list(order_by_score(fused)) == [1, 0, 2]


def test_rrf_k_default_is_sixty() -> None:
    assert RRF_K == 60
    assert rrf([np.array([0])], k=RRF_K)[0] == 1 / 60


def test_rrf_rejects_invalid_k() -> None:
    import pytest

    with pytest.raises(ValueError):
        rrf([np.array([0])], k=0)


def test_bm25_ranks_the_matching_document_first() -> None:
    ranker = Bm25Ranker([["ค่าไฟฟ้า", "ค้าง"], ["ค่าไฟ", "บ้าน"], ["รถ", "ยนต์"]])
    ranks = ranker.ranks(["ค่าไฟฟ้า"])
    assert ranks[0] == 0
    assert len(ranker) == 3


def test_bm25_handles_empty_corpus_and_empty_query() -> None:
    assert Bm25Ranker([]).ranks(["อะไรก็ได้"]).size == 0
    assert list(Bm25Ranker([["a"]]).ranks([])) == [0]
    assert list(Bm25Ranker([["a"]]).scores([])) == [0.0]
