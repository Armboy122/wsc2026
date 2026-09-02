"""ขอบเขตเสี่ยงของ plugin loader: manifest ผิดต้อง fail closed และ submit ต้องไม่ถึง LLM

ไม่ทดสอบทุก field ของ manifest แต่ทดสอบเฉพาะจุดที่ความล้มเหลวมีราคาแพง:
startup ที่ยอมรับ config ผิด, การเปิด submit action ให้โมเดล, และ schema ที่ drift
จาก Pydantic contracts จริง
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.config import load_settings
from app.plugins import PluginError, load_plugins
from app.plugins.manifest import PluginManifest

_OMS_MANIFEST = Path(__file__).resolve().parents[1] / "oms" / "plugin.yaml"


def _manifest_dict() -> dict:
    return yaml.safe_load(_OMS_MANIFEST.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict, *, directory: str = "oms") -> Path:
    plugin_dir = tmp_path / directory
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8"
    )
    return tmp_path


def test_real_oms_manifest_loads_and_builds_the_existing_tool() -> None:
    """critical path: OMS ถูก discover จาก manifest จริงและได้ OmsTool ตัวเดิม"""
    from app.contracts import ToolName
    from app.tools.oms_tool import OmsTool

    plugins = load_plugins(load_settings())

    assert len(plugins) == 2
    plugin = next(item for item in plugins if item.manifest.metadata.id is ToolName.OMS)
    assert isinstance(plugin.tool, OmsTool)
    assert plugin.response_policy is not None
    assert plugin.demo_behavior is not None

    voc_plugin = next(item for item in plugins if item.manifest.metadata.id is ToolName.VOC)
    assert voc_plugin.response_policy is not None
    assert voc_plugin.demo_behavior is not None
    assert voc_plugin.tool_definition.actions == (
        "list_categories",
        "prepare_case",
        "get_case",
    )


def test_llm_catalogue_hides_internal_submit_actions() -> None:
    """write safety: submit_* ต้องไม่ถูกโฆษณาให้โมเดลเลือกเอง"""
    plugin = load_plugins(load_settings())[0]

    actions = plugin.tool_definition.actions

    assert "submit_outage_with_ca" not in actions
    assert "submit_anonymous_outage" not in actions
    assert set(actions) == {
        "get_outage_by_ca",
        "prepare_outage_with_ca",
        "prepare_anonymous_outage",
    }


def test_disabled_plugin_is_not_registered(tmp_path: Path) -> None:
    payload = _manifest_dict()
    payload["metadata"]["enabled"] = False

    assert load_plugins(load_settings(), plugin_root=_write(tmp_path, payload)) == ()


def test_disabled_scaffold_with_unfinished_manifest_does_not_break_startup(tmp_path: Path) -> None:
    """โครงที่ ``add-plugin`` สร้างไว้ยังไม่มี action และยังไม่ได้ประกาศใน contracts

    ตราบใดที่ ``enabled`` ยังเป็น false ต้องข้ามไปเงียบ ๆ ไม่ใช่ทำให้ทั้งระบบเริ่มไม่ได้
    """
    scaffold = {
        "apiVersion": "pea.one/v1",
        "kind": "Plugin",
        "metadata": {
            "id": "billing_tool",
            "name": "TODO",
            "enabled": False,
            "category": "operational",
            "description": "TODO",
        },
        "runtime": {"factory": "app.plugins.billing.factory:create_plugin"},
        "operations": None,
    }
    _write(tmp_path, _manifest_dict(), directory="oms")
    _write(tmp_path, scaffold, directory="billing")

    loaded = load_plugins(load_settings(), plugin_root=tmp_path)

    assert [plugin.manifest.metadata.id.value for plugin in loaded] == ["oms_tool"]


def test_enabled_scaffold_that_is_still_unfinished_fails_closed(tmp_path: Path) -> None:
    """เปิดใช้งานทั้งที่ manifest ยังไม่สมบูรณ์ ต้องล้มตอน startup ไม่ใช่ปล่อยผ่าน"""
    scaffold = {
        "apiVersion": "pea.one/v1",
        "kind": "Plugin",
        "metadata": {
            "id": "billing_tool",
            "name": "TODO",
            "enabled": True,
            "category": "operational",
            "description": "TODO",
        },
        "runtime": {"factory": "app.plugins.billing.factory:create_plugin"},
        "operations": None,
    }

    with pytest.raises(PluginError):
        load_plugins(load_settings(), plugin_root=_write(tmp_path, scaffold, directory="billing"))


def test_manifest_that_exposes_submit_to_the_llm_fails_closed() -> None:
    payload = _manifest_dict()
    for operation in payload["operations"]:
        if operation["action"] == "submit_outage_with_ca":
            operation["exposure"] = "llm"

    with pytest.raises(ValueError, match="submit action ต้องเป็น internal"):
        PluginManifest.model_validate(payload)


def test_manifest_contract_drift_from_pydantic_fails_closed() -> None:
    """YAML ต้องไม่กลายเป็น schema ชุดที่สองที่หลุดจาก app/contracts.py"""
    payload = _manifest_dict()
    payload["operations"][0]["inputContract"] = "SomeOtherInput"

    with pytest.raises(ValueError, match="inputContract"):
        PluginManifest.model_validate(payload)


def test_untrusted_factory_path_is_rejected() -> None:
    payload = _manifest_dict()
    payload["runtime"]["factory"] = "os:system"

    with pytest.raises(ValueError, match="factory ต้องอยู่ใต้"):
        PluginManifest.model_validate(payload)


def test_malformed_manifest_raises_startup_error(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "broken"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text("apiVersion: pea.one/v1\nkind: [", encoding="utf-8")

    with pytest.raises(PluginError):
        load_plugins(load_settings(), plugin_root=tmp_path)


def test_duplicate_plugin_id_fails_closed(tmp_path: Path) -> None:
    payload = _manifest_dict()
    _write(tmp_path, payload, directory="oms")
    _write(tmp_path, payload, directory="oms_copy")

    with pytest.raises(PluginError, match="ปลั๊กอินซ้ำ"):
        load_plugins(load_settings(), plugin_root=tmp_path)


def test_plugin_aliases_are_compiled_into_llm_catalogue_guidance() -> None:
    plugins = load_plugins(load_settings())
    oms = next(plugin for plugin in plugins if plugin.manifest.metadata.id.value == "oms_tool")
    voc = next(plugin for plugin in plugins if plugin.manifest.metadata.id.value == "voc_tool")

    assert "เช็คไฟดับ" in oms.tool_definition.description
    assert "prepare_anonymous_outage" in oms.tool_definition.description
    assert "ดูประเภทเรื่องร้องเรียน" in voc.tool_definition.description
    assert "list_categories" in voc.tool_definition.description


def test_alias_file_cannot_advertise_an_unavailable_action(tmp_path: Path) -> None:
    root = _write(tmp_path, _manifest_dict())
    (root / "oms" / "aliases.md").write_text(
        "---\n"
        "rules:\n"
        "  - action: submit_outage_with_ca\n"
        "    phrases:\n"
        "      - ส่งเลย\n"
        "---\n",
        encoding="utf-8",
    )

    with pytest.raises(PluginError, match="plugin alias ไม่ถูกต้อง"):
        load_plugins(load_settings(), plugin_root=root)
