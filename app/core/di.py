"""The single runtime dependency shared by HTTP/WebSocket entry points: Knowledge."""

from __future__ import annotations

from app.knowledge.service import KnowledgeDocumentService

_knowledge_service: KnowledgeDocumentService | None = None


def set_knowledge_service(service: KnowledgeDocumentService) -> None:
    global _knowledge_service
    _knowledge_service = service


def get_knowledge_service() -> KnowledgeDocumentService:
    if _knowledge_service is None:
        raise RuntimeError("ยังไม่ได้เชื่อมต่อ Knowledge service เข้ากับ ADK Voice Agent")
    return _knowledge_service
