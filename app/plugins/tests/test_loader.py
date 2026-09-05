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
    """สำเนา manifest จริงของ oms ที่บังคับ ``enabled: true`` เสมอ

    D2.7 ย้าย oms_tool ขึ้น declarative tool contract แล้วปิดปลั๊กอิน Python ตัวจริงไว้
    (soft delete) การทดสอบ *shape* ของ manifest (validation, alias, schema subset ฯลฯ)
    ในไฟล์นี้ไม่เกี่ยวกับว่าปลั๊กอินตัวจริงเปิดอยู่ไหม จึงบังคับเปิดในสำเนานี้เสมอ
    """
    payload = yaml.safe_load(_OMS_MANIFEST.read_text(encoding="utf-8"))
    payload["metadata"]["enabled"] = True
    return payload


def _write(tmp_path: Path, payload: dict, *, directory: str = "oms") -> Path:
    plugin_dir = tmp_path / directory
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8"
    )
    return tmp_path


def test_real_oms_manifest_is_disabled_since_it_moved_to_the_declarative_contract() -> None:
    """D2.7: oms_tool ย้ายขึ้น declarative tool contract (DB) แล้ว — plugin.yaml ของมัน
    ถูกปิดไว้แบบ soft delete ไม่ถูก discover เป็น Python plugin อีกต่อไป มีแค่ VOC เหลืออยู่"""
    from app.contracts import ToolName

    plugins = load_plugins(load_settings())

    assert len(plugins) == 1
    voc_plugin = next(item for item in plugins if item.manifest.metadata.id is ToolName.VOC)
    assert voc_plugin.response_policy is not None
    assert voc_plugin.demo_behavior is not None
    assert voc_plugin.tool_definition.actions == (
        "list_categories",
        "prepare_case",
        "get_case",
    )


def test_llm_catalogue_hides_internal_submit_actions(tmp_path: Path) -> None:
    """write safety: submit_* ต้องไม่ถูกโฆษณาให้โมเดลเลือกเอง

    ใช้สำเนา manifest ของ oms ที่บังคับเปิดไว้ (ตัวจริงถูกปิดตั้งแต่ D2.7) เพราะเทสนี้
    ตรวจ *shape* ของ manifest ไม่ใช่ว่าปลั๊กอินตัวจริงเปิดอยู่ไหม
    """
    plugins = load_plugins(load_settings(), plugin_root=_write(tmp_path, _manifest_dict()))
    plugin = plugins[0]

    actions = plugin.tool_definition.actions

    assert "submit_outage_with_ca" not in actions
    assert "submit_anonymous_outage" not in actions
    assert set(actions) == {
        "get_outage_by_ca",
        "prepare_outage_with_ca",
        "prepare_anonymous_outage",
    }


def test_cross_plugin_demo_behavior_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """demo behavior ของ oms ต้องอ้างเฉพาะ oms — ยืมของอีกปลั๊กอินมาต้องล้มปิด

    ``oms.factory`` ตอนนี้เป็นแค่ stub เพราะ ``OmsTool`` จริงถูกลบไปแล้วตอน D2.7 ย้าย oms
    ขึ้น declarative tool contract (ดู app/plugins/oms/factory.py) แต่ยังทดสอบพฤติกรรม
    เดียวกันได้: monkeypatch ให้คืน demo behavior ของปลั๊กอินอื่นแทนของตัวเอง
    """
    from app.plugins.oms import factory as oms_factory
    from app.plugins.oms.factory import _InertOmsTool
    from app.plugins.runtime import PluginRuntime
    from app.plugins.voc.demo import VocDemoBehavior

    monkeypatch.setattr(
        oms_factory,
        "create_plugin",
        lambda settings: PluginRuntime(tool=_InertOmsTool(), demo_behavior=VocDemoBehavior()),
    )

    with pytest.raises(PluginError, match="demo behavior"):
        load_plugins(load_settings(), plugin_root=_write(tmp_path, _manifest_dict()))


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


def test_manifest_submit_action_without_write_confirm_policy_fails_closed() -> None:
    """D1.6: policy ที่ tool ประกาศเองเป็น untrusted — submitAction ต้องคู่กับ write_confirm เท่านั้น"""
    payload = _manifest_dict()
    for operation in payload["operations"]:
        if operation["action"] == "prepare_outage_with_ca":
            operation["policy"] = "plain_read"

    with pytest.raises(ValueError, match="มี submitAction แต่ policy ต้องเป็น write_confirm"):
        PluginManifest.model_validate(payload)


def test_manifest_write_confirm_without_prepare_submit_pairing_fails_closed() -> None:
    """D1.6: write_confirm บน read operation (ไม่มีคู่ prepare→submit) ต้อง reject"""
    payload = _manifest_dict()
    for operation in payload["operations"]:
        if operation["action"] == "get_outage_by_ca":
            operation["policy"] = "write_confirm"

    with pytest.raises(ValueError, match="ประกาศ write_confirm แต่ไม่มีคู่ prepare→submit"):
        PluginManifest.model_validate(payload)


def test_manifest_operation_without_policy_defaults_closed_even_if_exposure_says_llm() -> None:
    """D1.6/§4.5: ไม่ประกาศ policy => plain_read + บังคับ internal เสมอ ไม่ว่า exposure จะเขียนว่าอะไร"""
    payload = _manifest_dict()
    for operation in payload["operations"]:
        if operation["action"] == "get_outage_by_ca":
            del operation["policy"]

    manifest = PluginManifest.model_validate(payload)
    operation = next(op for op in manifest.operations if op.action.value == "get_outage_by_ca")

    assert operation.effective_policy.value == "plain_read"
    assert "get_outage_by_ca" not in {op.action.value for op in manifest.llm_actions}


def test_manifest_output_contract_drift_from_pydantic_fails_closed() -> None:
    """outputContract ยังอ้างชื่อคลาส Pydantic เดิม — D2.2 เปลี่ยนแค่ input เป็น inputSchema"""
    payload = _manifest_dict()
    payload["operations"][0]["outputContract"] = "SomeOtherOutput"

    with pytest.raises(ValueError, match="outputContract"):
        PluginManifest.model_validate(payload)


def test_manifest_input_schema_outside_the_allowed_subset_fails_closed() -> None:
    """D2.2/D1.2: inputSchema ที่หลุด subset ต้อง reject ตอน startup ไม่ใช่รอพังตอนรัน"""
    payload = _manifest_dict()
    payload["operations"][0]["inputSchema"] = {
        "type": "object",
        "properties": {"caNumber": {"type": "string", "pattern": "^[0-9]{12}$"}},
        "required": ["caNumber"],
        "additionalProperties": False,
    }

    with pytest.raises(ValueError, match="inputSchema"):
        PluginManifest.model_validate(payload)


def test_load_plugins_fails_closed_when_input_schema_breaks_the_subset(tmp_path: Path) -> None:
    """D2.2 เกณฑ์เสร็จ: manifest ที่ schema ผิด = startup ล้ม (fail closed)"""
    payload = _manifest_dict()
    payload["operations"][0]["inputSchema"] = {
        "type": "object",
        "properties": {"caNumber": {"type": "string", "minLength": 12}},
        "required": ["caNumber"],
        "additionalProperties": False,
    }

    with pytest.raises(PluginError, match="manifest ไม่ถูกต้อง"):
        load_plugins(load_settings(), plugin_root=_write(tmp_path, payload))


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


def test_plugin_aliases_are_compiled_into_llm_catalogue_guidance(tmp_path: Path) -> None:
    # oms ตัวจริงถูกปิดตั้งแต่ D2.7 (ย้ายขึ้น declarative tool contract) จึงใช้สำเนาที่บังคับ
    # เปิดไว้แทนสำหรับตรวจ shape ของ alias guidance (คัดลอก aliases.md จริงมาด้วย เพราะ
    # _write() เขียนแค่ plugin.yaml) — voc ยังเป็น Python plugin ตัวจริง ตรวจจาก root จริงได้ตามเดิม
    root = _write(tmp_path, _manifest_dict())
    (root / "oms" / "aliases.md").write_text(
        (_OMS_MANIFEST.parent / "aliases.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    oms_plugins = load_plugins(load_settings(), plugin_root=root)
    oms = oms_plugins[0]
    voc = next(plugin for plugin in load_plugins(load_settings()) if plugin.manifest.metadata.id.value == "voc_tool")

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
