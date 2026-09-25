"""Opt-in real-embedding retrieval test (self-hosted ``BAAI/bge-m3``).

Deselected by default (``-m 'not model'`` in ``addopts``). The test skips unless the model is
already present in the local Hugging Face cache, and it forces ``HF_HUB_OFFLINE=1`` before
loading, so it never downloads a model or touches the network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.index import BgeM3Embedder, KnowledgeIndex

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "knowledge" / "source"
ALIAS_ROOT = ROOT / "knowledge" / "aliases"

MODEL_ID = "BAAI/bge-m3"
# The 2026-09-26 research run (goal table) scored 29/35 correct answers with this Q&A-first
# hybrid approach; Q&A-lane hit@2 in that run was 34/35. Gate on the headline number.
MIN_HITS = 29


def _model_is_cached() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    cached = try_to_load_from_cache(MODEL_ID, "config.json")
    return isinstance(cached, str)


@pytest.mark.model
def test_bge_m3_qa_lane_hit_at_2_on_paraphrases() -> None:
    if not _model_is_cached():
        pytest.skip(f"{MODEL_ID} is not present in the local Hugging Face cache")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

    catalog = KnowledgeCatalog(SOURCE_ROOT, alias_root=ALIAS_ROOT)
    # Paraphrases are held out of the indexed Q&A text, as in the research harness, so the
    # test measures retrieval rather than memorising the query.
    index = KnowledgeIndex(
        catalog, embedder=BgeM3Embedder(), include_qa_paraphrases=False
    )

    pairs = [
        (unit, paraphrase) for unit in index.qa_units for paraphrase in unit.paraphrases
    ]
    assert len(pairs) == 35

    hits = 0
    misses: list[str] = []
    for unit, paraphrase in pairs:
        result = index.search(paraphrase)
        top_two = {hit.source_id for hit in result.qa}
        if unit.source_id in top_two:
            hits += 1
        else:
            misses.append(f"{unit.source_id} :: {paraphrase}")

    print(f"Q&A-lane hit@2 (paraphrases held out): {hits}/{len(pairs)}")
    for miss in misses:
        print(f"  miss: {miss}")
    assert hits >= MIN_HITS, f"hit@2 regressed below the research run: {hits}/{len(pairs)}"
