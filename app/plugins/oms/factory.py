"""Stub factory ที่คงให้ manifest ของ oms (ถูกปิดแบบ soft delete) ยัง load ได้ในเทสที่
force-enable สำเนาของมัน — D2.7

``oms_tool`` ย้ายขึ้น declarative tool contract (DB) แล้ว (ดู ``scripts/seed_oms_tool.py``
และ ``app/plugins/oms/declarative_shape.py``) ``plugin.yaml`` ถูกปิดไว้ (``enabled: false``)
จึง**ไม่ถูกเรียกโดย ``app/main.py`` อีกต่อไป** — โมดูลนี้เหลืออยู่เพียงเพื่อให้เทสที่ตรวจ
*shape* ของ manifest (schema subset, alias guidance, การตรวจ manifest ผิด ฯลฯ ใน
``app/plugins/tests/test_loader.py``) force-enable สำเนาของ manifest แล้ว ``load_plugins()``
ได้จริงโดยไม่ต้องคืนชีพ ``OmsTool`` เดิม (คลาสที่ยิง HTTP จริงถูกลบไปแล้ว) — tool ที่คืนที่นี่
ไม่มีพฤติกรรมจริง เทสเหล่านั้นไม่เรียก ``.execute()`` ของมันเลย
"""

from __future__ import annotations

from typing import Any

from app.contracts import ToolName
from app.plugins.oms.demo import OmsDemoBehavior
from app.plugins.oms.response import OmsResponsePolicy
from app.plugins.runtime import PluginRuntime


class _InertOmsTool:
    """ไม่มีพฤติกรรมจริง — มีไว้ให้ manifest ที่ force-enable ในเทสเท่านั้น validate ผ่าน"""

    name = ToolName.OMS

    async def execute(self, call: Any, context: Any) -> Any:  # pragma: no cover - ไม่ถูกเรียกจริง
        raise NotImplementedError("oms_tool ย้ายขึ้น declarative tool contract แล้ว")

    def reset(self) -> None:
        pass


def create_plugin(settings: Any) -> PluginRuntime:
    return PluginRuntime(
        tool=_InertOmsTool(),
        response_policy=OmsResponsePolicy(),
        demo_behavior=OmsDemoBehavior(),
    )
