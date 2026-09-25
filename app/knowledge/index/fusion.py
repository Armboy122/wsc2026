"""Reciprocal Rank Fusion and rank/score helpers.

Ranks are 0-based per document (0 = best) and computed with a stable sort so equal scores
always break by corpus order, which keeps retrieval deterministic across processes.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

RRF_K = 60


def ranks_from_scores(scores: np.ndarray) -> np.ndarray:
    """Return the 0-based descending rank of every document in ``scores``."""
    values = np.asarray(scores, dtype=np.float64)
    if values.size == 0:
        return np.empty(0, dtype=np.int64)
    order = np.argsort(-values, kind="stable")
    ranks = np.empty(values.shape, dtype=np.int64)
    ranks[order] = np.arange(values.size, dtype=np.int64)
    return ranks


def rrf(rank_arrays: Sequence[np.ndarray], *, k: int = RRF_K) -> np.ndarray:
    """Fuse ranked lists: ``sum(1 / (k + rank))`` per document."""
    if k < 1:
        raise ValueError("RRF k must be at least 1")
    if not rank_arrays:
        return np.empty(0, dtype=np.float64)
    size = np.asarray(rank_arrays[0]).size
    fused = np.zeros(size, dtype=np.float64)
    for ranks in rank_arrays:
        fused += 1.0 / (k + np.asarray(ranks, dtype=np.float64))
    return fused


def order_by_score(scores: np.ndarray) -> np.ndarray:
    """Return document indices best-first, stable for ties."""
    values = np.asarray(scores, dtype=np.float64)
    if values.size == 0:
        return np.empty(0, dtype=np.int64)
    return np.argsort(-values, kind="stable")


def as_python_float(value: object) -> float:
    """Return a plain Python float; numpy scalars and 0-d arrays expose ``item()``."""
    return np.asarray(value).item()
