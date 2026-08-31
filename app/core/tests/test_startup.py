"""ทดสอบการตรวจสอบความถูกต้องและการเชื่อมส่วนประกอบเมื่อเริ่มระบบ"""

from __future__ import annotations

from typing import Any

import pytest

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


def test_validate_tool_registry_accepts_frozenset_property() -> None:
    """ทดสอบย้อนหลัง: getattr(registry, 'names')() เคยล้มเหลวเมื่อ names เป็นคุณสมบัติ"""
    validate_tool_registry(_FrozenNamesRegistry())


def test_validate_tool_registry_accepts_callable_names() -> None:
    validate_tool_registry(_CallableNamesRegistry())


def test_validate_tool_registry_accepts_iterable_names() -> None:
    validate_tool_registry(_ListNamesRegistry())


def test_validate_tool_registry_rejects_missing_tool() -> None:
    class IncompleteRegistry:
        names = frozenset({ToolName.KNOWLEDGE, ToolName.SABUY, ToolName.VOC})

    with pytest.raises(RuntimeError):
        validate_tool_registry(IncompleteRegistry())


def test_validate_tool_registry_rejects_extra_tool() -> None:
    extra = "unknown_tool"

    class ExtraRegistry:
        names = frozenset({*REQUIRED_TOOLS, extra})

    with pytest.raises(RuntimeError):
        validate_tool_registry(ExtraRegistry())
