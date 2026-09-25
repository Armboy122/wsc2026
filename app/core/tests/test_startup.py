"""ทดสอบการตรวจสอบความถูกต้องและการเชื่อมส่วนประกอบเมื่อเริ่มระบบ"""

from __future__ import annotations

from typing import Any

import pytest

from app.backends.full_document_knowledge import FullDocumentKnowledgeBackend
from app.contracts import ToolName
from app.core.startup import REQUIRED_TOOLS, validate_tool_registry


class _FrozenNamesRegistry:
    """จำลองคุณสมบัติ frozenset ของ ToolRegistry.names ที่ใช้งานจริง"""

    @property
    def names(self) -> frozenset[ToolName]:
        return frozenset(REQUIRED_TOOLS)


class _CallableNamesRegistry:
    def names(self) -> set[ToolName]:
        return set(REQUIRED_TOOLS)


class _ListNamesRegistry:
    names = list(REQUIRED_TOOLS)


def test_runtime_wires_deterministic_knowledge_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing the application constructs the deterministic catalog and no Knowledge model client."""
    monkeypatch.setenv("MAIN_LLM_PROVIDER", "demo")
    from app import main

    from app.core.di import get_knowledge_service
    from app.knowledge.service import KnowledgeDocumentService
    from app.llm import JudgeLLMClient

    assert isinstance(main.knowledge_service, KnowledgeDocumentService)
    assert get_knowledge_service() is main.knowledge_service
    assert len(main.knowledge_catalog) > 0
    assert isinstance(main.knowledge_backend, FullDocumentKnowledgeBackend)
    assert isinstance(main.judge_llm_client, JudgeLLMClient)


def test_validate_tool_registry_accepts_frozenset_property() -> None:
    """ทดสอบย้อนหลัง: getattr(registry, 'names')() เคยล้มเหลวเมื่อ names เป็นคุณสมบัติ"""
    validate_tool_registry(_FrozenNamesRegistry())


def test_validate_tool_registry_accepts_callable_names() -> None:
    validate_tool_registry(_CallableNamesRegistry())


def test_validate_tool_registry_accepts_iterable_names() -> None:
    validate_tool_registry(_ListNamesRegistry())


def test_validate_tool_registry_rejects_missing_built_in_tool() -> None:
    """Knowledge เป็น built-in ที่ขาดไม่ได้ แม้จะมีเครื่องมืออื่นลงทะเบียนอยู่"""
    class WithoutKnowledgeRegistry:
        names = frozenset({ToolName.OMS})

    with pytest.raises(RuntimeError):
        validate_tool_registry(WithoutKnowledgeRegistry())


def test_validate_tool_registry_accepts_plugin_supplied_tools() -> None:
    """เครื่องมือปฏิบัติการมาจากปลั๊กอิน จึงเพิ่ม/ปิดได้โดยไม่ต้องแก้ startup"""
    class WithPluginRegistry:
        names = frozenset({*REQUIRED_TOOLS, ToolName.OMS})

    class KnowledgeOnlyRegistry:
        names = frozenset(REQUIRED_TOOLS)

    validate_tool_registry(WithPluginRegistry())
    validate_tool_registry(KnowledgeOnlyRegistry())
