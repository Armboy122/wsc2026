"""Global test setup: keep the knowledge index offline and out of the repository.

The suite must never load torch/sentence-transformers or download a model. ``app.main``
builds the real index manager at import time, so tests force the deterministic fake
embedder and a throwaway cache directory before any application module is imported.
"""

from __future__ import annotations

import os
import tempfile

os.environ["KNOWLEDGE_EMBEDDER"] = "fake"
os.environ["KNOWLEDGE_INDEX_DIR"] = tempfile.mkdtemp(prefix="pea-knowledge-index-test-")
