"""ประกอบ OmsTool จาก settings ที่มีอยู่แล้ว โดยไม่เปลี่ยนพฤติกรรมของ OMS"""

from __future__ import annotations

from typing import Any

from app.plugins.oms.demo import OmsDemoBehavior
from app.plugins.oms.response import OmsResponsePolicy
from app.plugins.runtime import PluginRuntime
from app.tools.oms_tool import OmsTool


def create_plugin(settings: Any) -> PluginRuntime:
    """ประกอบ runtime contributions ทั้งหมดที่ OMS เป็นเจ้าของ"""
    return PluginRuntime(
        tool=OmsTool(
            settings.oms_base_url,
            settings.oms_timeout_seconds,
            api_key=settings.oms_api_key,
        ),
        response_policy=OmsResponsePolicy(),
        demo_behavior=OmsDemoBehavior(),
    )
