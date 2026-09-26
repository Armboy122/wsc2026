"""Shared fixtures for the offline RAG evaluation tests.

Everything here is offline: the deterministic ``FakeEmbedder``, the real approved corpus
read-only, no network, no model download, no ``pi``/Gemini subprocess.
"""

from __future__ import annotations

import pytest

from app.knowledge.index import KnowledgeIndex
from evaluation.rag.dataset import EvalQuestion, load_dataset
from evaluation.rag.retrieval_eval import build_index


@pytest.fixture(scope="session")
def dataset() -> tuple[EvalQuestion, ...]:
    return load_dataset()


@pytest.fixture(scope="session")
def holdout_index() -> KnowledgeIndex:
    """The production index with the held-out paraphrases removed from the indexed Q&A text."""
    return build_index("fake", include_qa_paraphrases=False)
