"""Embedding seams for the knowledge index.

Importing this module never imports torch or sentence-transformers: the real model is loaded
lazily on first use inside :class:`BgeM3Embedder`. ``FakeEmbedder`` is a deterministic,
offline stand-in used by the test suite.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import numpy as np

from app.knowledge.index.tokenize import tokenize

DEFAULT_FAKE_DIM = 256


@runtime_checkable
class Embedder(Protocol):
    """Minimal seam so a hosted embedding model can replace the self-hosted one."""

    @property
    def model_id(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class FakeEmbedder:
    """Deterministic hashing embedder: same text always yields the same unit vector.

    Hashing uses ``hashlib`` (not ``hash``) so results never depend on ``PYTHONHASHSEED``.
    """

    def __init__(self, dim: int = DEFAULT_FAKE_DIM) -> None:
        if dim < 1:
            raise ValueError("dim must be at least 1")
        self._dim = dim

    @property
    def model_id(self) -> str:
        return f"fake-hash-v1-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float64)
        return np.vstack([self._embed(text) for text in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)

    def _embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self._dim, dtype=np.float64)
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self._dim
            vector[index] += 1.0 if digest[8] & 1 else -1.0
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return vector
        return vector / norm


class BgeM3Embedder:
    """Self-hosted ``BAAI/bge-m3`` on CPU, normalized, loaded on first use only."""

    MODEL_ID = "BAAI/bge-m3"
    DIM = 1024

    def __init__(
        self,
        model_id: str = MODEL_ID,
        *,
        max_seq_length: int = 1024,
        batch_size: int = 8,
    ) -> None:
        self._model_id = model_id
        self._max_seq_length = max_seq_length
        self._batch_size = batch_size
        self._model = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return self.DIM

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        model = self._load_model()
        vectors = model.encode(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]

    def _load_model(self):
        if self._model is None:
            # Lazy on purpose: keeps torch out of import-time dependencies.
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(self._model_id, device="cpu")
            model.max_seq_length = self._max_seq_length
            self._model = model
        return self._model
