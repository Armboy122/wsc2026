"""Plugin runtime settings for legacy OMS/VOC plugin tests.

Story 3 Ticket 001 removed OMS/VOC settings from the application; the plugin modules are
unreferenced by the running app and are deleted in Story 3 Ticket 002.
"""

from __future__ import annotations

from types import SimpleNamespace


def legacy_plugin_settings() -> SimpleNamespace:
    return SimpleNamespace(
        oms_base_url="http://127.0.0.1:8080/api/v1/oms",
        oms_timeout_seconds=5.0,
        oms_api_key=None,
        voc_base_url="http://127.0.0.1:8080/api/v1/voc",
        voc_timeout_seconds=5.0,
        voc_api_key=None,
        voc_consent_notice_version="VOC-PDPA-DEMO-1.0",
    )
