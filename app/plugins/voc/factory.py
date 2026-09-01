"""Construct the VOC REST tool from runtime settings."""

from __future__ import annotations

from typing import Any

from app.tools.voc_tool import VocTool


def create_plugin(settings: Any) -> VocTool:
    return VocTool(
        base_url=settings.voc_base_url,
        timeout_seconds=settings.voc_timeout_seconds,
        api_key=settings.voc_api_key,
    )
