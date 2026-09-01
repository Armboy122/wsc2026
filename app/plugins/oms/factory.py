"""ประกอบ OmsTool จาก settings ที่มีอยู่แล้ว โดยไม่เปลี่ยนพฤติกรรมของ OMS"""

from __future__ import annotations

from typing import Any

from app.tools.oms_tool import OmsTool


def create_plugin(settings: Any) -> OmsTool:
    """สร้างเครื่องมือ OMS หนึ่งตัวตาม configuration ที่ manifest อ้างถึง"""
    return OmsTool(
        settings.oms_base_url,
        settings.oms_timeout_seconds,
        api_key=settings.oms_api_key,
    )
