"""ค้นหาและประกอบปลั๊กอินภายนอกจาก manifest ตอน startup

loader อ่าน ``plugin.yaml`` ทุกไฟล์ใต้ ``app/plugins/`` เพียงครั้งเดียวตอนเริ่มระบบ
แล้ว compile เป็นแค็ตตาล็อกสั้นสำหรับ LLM ตัวโมเดลจึงไม่เคยเห็น YAML ดิบ
manifest ที่ผิดหรือ config ที่ขาดจะทำให้ startup ล้มเหลวแบบ fail closed เสมอ
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import ValidationError

from app.contracts import ToolName
from app.llm.models import ToolDefinition
from app.plugins.manifest import PluginManifest

_MANIFEST_FILENAME = "plugin.yaml"
_PLUGIN_ROOT = Path(__file__).resolve().parent


class PluginError(RuntimeError):
    """manifest หรือ factory ของปลั๊กอินใช้งานไม่ได้"""


class PluginFactory(Protocol):
    """factory ที่ manifest ชี้ไป ต้องคืนเครื่องมือหนึ่งตัวจาก settings ที่มีอยู่"""

    def __call__(self, settings: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    """ปลั๊กอินที่ผ่านการตรวจสอบและประกอบเป็นเครื่องมือแล้ว"""

    manifest: PluginManifest
    tool: Any

    @property
    def tool_definition(self) -> ToolDefinition:
        """แค็ตตาล็อกที่ LLM เห็น โดยตัด operation ที่เป็น internal ออก"""
        return ToolDefinition(
            name=self.manifest.metadata.id,
            description=" ".join(self.manifest.metadata.description.split()),
            actions=tuple(operation.action.value for operation in self.manifest.llm_actions),
        )


def load_plugins(settings: Any, *, plugin_root: Path | None = None) -> tuple[LoadedPlugin, ...]:
    """โหลดปลั๊กอินที่เปิดใช้งานทั้งหมดตามลำดับชื่อไดเรกทอรีที่คงที่"""
    root = plugin_root or _PLUGIN_ROOT
    loaded: list[LoadedPlugin] = []
    seen: set[ToolName] = set()
    for manifest_path in sorted(root.glob(f"*/{_MANIFEST_FILENAME}")):
        manifest = _read_manifest(manifest_path)
        if not manifest.metadata.enabled:
            continue
        if manifest.metadata.id in seen:
            raise PluginError(f"ปลั๊กอินซ้ำ: {manifest.metadata.id.value}")
        seen.add(manifest.metadata.id)
        loaded.append(LoadedPlugin(manifest=manifest, tool=_build_tool(manifest, settings)))
    return tuple(loaded)


def _read_manifest(path: Path) -> PluginManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise PluginError(f"อ่าน manifest ไม่ได้: {path.name}") from error
    if not isinstance(raw, dict):
        raise PluginError(f"manifest ต้องเป็น mapping: {path.name}")
    try:
        return PluginManifest.model_validate(raw)
    except ValidationError as error:
        raise PluginError(f"manifest ไม่ถูกต้อง ({path.parent.name}): {error}") from error


def _build_tool(manifest: PluginManifest, settings: Any) -> Any:
    """import factory จาก path ที่ manifest เชื่อถือได้ แล้วสร้างเครื่องมือหนึ่งตัว"""
    module_path, _, attribute = manifest.runtime.factory.partition(":")
    try:
        factory = getattr(import_module(module_path), attribute)
    except (ImportError, AttributeError) as error:
        raise PluginError(f"โหลด factory ไม่ได้: {manifest.runtime.factory}") from error
    if not callable(factory):
        raise PluginError(f"factory เรียกใช้ไม่ได้: {manifest.runtime.factory}")
    try:
        tool = factory(settings)
    except Exception as error:  # noqa: BLE001 - แปลงเป็น startup error ที่อ่านเข้าใจได้
        raise PluginError(f"สร้างเครื่องมือของปลั๊กอิน {manifest.metadata.id.value} ไม่สำเร็จ") from error
    if getattr(tool, "name", None) is not manifest.metadata.id:
        raise PluginError(
            f"เครื่องมือที่ factory คืนมาไม่ตรงกับ metadata.id: {manifest.metadata.id.value}"
        )
    return tool
