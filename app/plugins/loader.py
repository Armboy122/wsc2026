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
from app.plugins.runtime import PluginRuntime

_MANIFEST_FILENAME = "plugin.yaml"
_PLUGIN_ROOT = Path(__file__).resolve().parent


class PluginError(RuntimeError):
    """manifest หรือ factory ของปลั๊กอินใช้งานไม่ได้"""


class PluginFactory(Protocol):
    """factory ที่ manifest ชี้ไป ต้องคืน runtime bundle จาก settings"""

    def __call__(self, settings: Any) -> PluginRuntime: ...


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    """ปลั๊กอินที่ผ่านการตรวจสอบและประกอบ runtime contributions แล้ว"""

    manifest: PluginManifest
    runtime: PluginRuntime

    @property
    def tool(self) -> Any:
        return self.runtime.tool

    @property
    def response_policy(self) -> Any:
        return self.runtime.response_policy

    @property
    def demo_behavior(self) -> Any:
        return self.runtime.demo_behavior

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
        raw = _read_yaml(manifest_path)
        # ปลั๊กอินที่ปิดอยู่ต้องไม่ทำให้ระบบล้ม เพราะโครงที่ยังเขียนไม่เสร็จก็อยู่ในสถานะนี้
        if not _is_enabled(raw):
            continue
        manifest = _validate_manifest(raw, manifest_path)
        if manifest.metadata.id in seen:
            raise PluginError(f"ปลั๊กอินซ้ำ: {manifest.metadata.id.value}")
        seen.add(manifest.metadata.id)
        loaded.append(LoadedPlugin(manifest=manifest, runtime=_build_runtime(manifest, settings)))
    return tuple(loaded)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise PluginError(f"อ่าน manifest ไม่ได้: {path.name}") from error
    if not isinstance(raw, dict):
        raise PluginError(f"manifest ต้องเป็น mapping: {path.name}")
    return raw


def _is_enabled(raw: dict[str, Any]) -> bool:
    """อ่านสถานะเปิดใช้งานก่อน validate เพื่อให้โครงที่ยังไม่เสร็จอยู่ร่วมใน repo ได้

    ต้องเป็น ``true`` แบบชัดเจนเท่านั้น ค่าที่กำกวมหรือหายไปถือว่าปิดไว้ (fail closed)
    """
    metadata = raw.get("metadata")
    return isinstance(metadata, dict) and metadata.get("enabled") is True


def _validate_manifest(raw: dict[str, Any], path: Path) -> PluginManifest:
    try:
        return PluginManifest.model_validate(raw)
    except ValidationError as error:
        raise PluginError(f"manifest ไม่ถูกต้อง ({path.parent.name}): {error}") from error


def _build_runtime(manifest: PluginManifest, settings: Any) -> PluginRuntime:
    """Import one trusted factory and validate its explicit contribution bundle."""
    module_path, _, attribute = manifest.runtime.factory.partition(":")
    try:
        factory = getattr(import_module(module_path), attribute)
    except (ImportError, AttributeError) as error:
        raise PluginError(f"โหลด factory ไม่ได้: {manifest.runtime.factory}") from error
    if not callable(factory):
        raise PluginError(f"factory เรียกใช้ไม่ได้: {manifest.runtime.factory}")
    try:
        runtime = factory(settings)
    except Exception as error:  # noqa: BLE001 - แปลงเป็น startup error ที่อ่านเข้าใจได้
        raise PluginError(f"สร้าง runtime ของปลั๊กอิน {manifest.metadata.id.value} ไม่สำเร็จ") from error
    if not isinstance(runtime, PluginRuntime):
        raise PluginError(f"factory ของ {manifest.metadata.id.value} ต้องคืน PluginRuntime")
    if getattr(runtime.tool, "name", None) is not manifest.metadata.id:
        raise PluginError(
            f"เครื่องมือที่ factory คืนมาไม่ตรงกับ metadata.id: {manifest.metadata.id.value}"
        )
    return runtime
