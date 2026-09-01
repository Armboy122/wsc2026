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

    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin.manifest.metadata.id is ToolName.OMS
    assert isinstance(plugin.tool, OmsTool)


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
