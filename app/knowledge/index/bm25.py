"""Lexical BM25 ranking over tokenized knowledge units (rank-bm25)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from rank_bm25 import BM25Okapi

from app.knowledge.index.fusion import ranks_from_scores


class Bm25Ranker:
    """Immutable BM25 index over an ordered list of token lists."""

    def __init__(self, tokenized_documents: Sequence[Sequence[str]]) -> None:
        self._documents: list[list[str]] = [list(document) for document in tokenized_documents]
        self._bm25 = BM25Okapi(self._documents) if self._documents else None

    def __len__(self) -> int:
        return len(self._documents)

    def scores(self, query_tokens: Sequence[str]) -> np.ndarray:
        """BM25 score per document; zeros for an empty corpus or query."""
        if self._bm25 is None or not query_tokens:
            return np.zeros(len(self._documents), dtype=np.float64)
        return np.asarray(self._bm25.get_scores(list(query_tokens)), dtype=np.float64)

    def ranks(self, query_tokens: Sequence[str]) -> np.ndarray:
        """0-based descending rank per document (0 = best)."""
        return ranks_from_scores(self.scores(query_tokens))
