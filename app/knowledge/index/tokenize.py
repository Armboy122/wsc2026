"""Thai/English tokenization shared by BM25 and the deterministic test embedder.

PyThaiNLP's ``newmm`` engine uses the dictionary bundled with the package, so tokenization
is fully offline. Tokens are lowercased and whitespace/punctuation-only tokens are dropped.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pythainlp.tokenize import word_tokenize

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


@lru_cache(maxsize=4096)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in word_tokenize(text.lower(), engine="newmm", keep_whitespace=False)
        if token.strip() and not _NON_WORD.fullmatch(token)
    )


def tokenize(text: str) -> list[str]:
    """Return lowercase word tokens for ``text``; never raises for empty input."""
    if not text or not text.strip():
        return []
    return list(_tokenize_cached(text))
