"""Approved-Knowledge availability for the public ``GET /health`` contract.

The conversational Knowledge capability now lives in ``app/agent/adk_agent.py`` as the
``search_knowledge`` tool over the deterministic local index. This module only exposes
whether approved Knowledge is configured, so ``/health`` can report ``knowledgeBackend``
without any document selection or model-facing catalog.
"""

from __future__ import annotations

from app.knowledge.catalog import KnowledgeCatalog


class KnowledgeDocumentService:
    """Hold the approved Knowledge catalog for availability checks (no selection)."""

    def __init__(self, catalog: KnowledgeCatalog) -> None:
        self._catalog = catalog

    @property
    def catalog(self) -> KnowledgeCatalog:
        return self._catalog
