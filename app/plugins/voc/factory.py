"""Construct the VOC REST tool from runtime settings."""

from __future__ import annotations

from typing import Any

from app.plugins.runtime import PluginRuntime
from app.plugins.voc.demo import VocDemoBehavior
from app.plugins.voc.flow import VocGuidedFlow
from app.plugins.voc.response import VocResponsePolicy
from app.tools.voc_tool import VocTool


def create_plugin(settings: Any) -> PluginRuntime:
    tool = VocTool(
        base_url=settings.voc_base_url,
        timeout_seconds=settings.voc_timeout_seconds,
        api_key=settings.voc_api_key,
    )
    return PluginRuntime(
        tool=tool,
        response_policy=VocResponsePolicy(),
        demo_behavior=VocDemoBehavior(),
        guided_flow=VocGuidedFlow(
            tool,
            consent_notice_version=getattr(
                settings, "voc_consent_notice_version", "VOC-PDPA-DEMO-1.0"
            ),
        ),
    )
