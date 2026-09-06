"""ทดสอบการตีความผล POST /tools/try ที่หน้า admin ใช้จริง — D3.5/A2

ปัญหาที่พิสูจน์ก่อนแก้ (ดูรายงานท้ายงาน A2):
- backend คืน ``ok: true`` ทุกครั้งที่ได้ HTTP response จริง ไม่ว่า status code จะเป็นอะไร
  (ยืนยันด้วย ``app/core/tool_admin.py::_try_operation_raw`` บรรทัดคืนผลตอนท้าย และ
  ``tests/test_admin_try_operation.py::test_try_reports_*``)
- ฝั่งเว็บเดิม (``web/admin.js::renderTryOutcome``) แสดง "สำเร็จ · HTTP <code>" ให้ทุกกรณีที่
  ``data.ok === true`` โดยไม่ตรวจ status code เลย — ผู้ดูแลจึงเห็น "สำเร็จ" แม้ปลายทางตอบ 401/500

เทสนี้เรียก ``describeTryOutcome`` ของ ``web/admin-form.js`` ตรง ๆ ผ่าน Node (ฟังก์ชัน pure
ไม่แตะ DOM — แพตเทิร์นเดียวกับ ``tests/test_admin_edit_payload.py::run_node``) ซึ่งเป็นตรรกะ
ตัวเดียวกับที่ ``web/admin.js::renderTryOutcome`` เรียกใช้จริงตอน render ผล — ไม่ได้จำลองใหม่
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FORM = ROOT / "web" / "admin-form.js"
ADMIN_JS = ROOT / "web" / "admin.js"


def run_node(expression: str) -> Any:
    script = f'import * as form from "{FORM.as_uri()}"; {expression}'
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def describe(data: dict[str, Any]) -> dict[str, Any]:
    return run_node(
        "console.log(JSON.stringify(form.describeTryOutcome(" + json.dumps(data) + ")));"
    )


# --------------------------------------------------------------- 2xx = สำเร็จ --


def test_200_is_success_not_error() -> None:
    outcome = describe({"ok": True, "response": {"statusCode": 200, "elapsedMs": 12.3}})
    assert outcome["kind"] == "success"
    assert outcome["cssClass"] == "try-status-ok"
    assert "200" in outcome["label"]
    # ต้องอธิบายว่า HTTP สำเร็จยังไม่พิสูจน์ว่า AI ใช้ tool ได้ครบ
    assert "note" in outcome and "AI" in outcome["note"]


def test_204_empty_body_is_success() -> None:
    """204/body ว่างต้องไม่กลายเป็น parse failure — ยังจัดเป็น HTTP สำเร็จ"""
    outcome = describe({"ok": True, "response": {"statusCode": 204, "elapsedMs": 3.0}})
    assert outcome["kind"] == "success"
    assert outcome["cssClass"] == "try-status-ok"


# -------------------------------------------------------- 4xx/5xx = ไม่สำเร็จ --


def test_401_is_not_shown_as_success_and_hints_credential() -> None:
    outcome = describe({"ok": True, "response": {"statusCode": 401, "elapsedMs": 8.0}})
    assert outcome["kind"] == "http_error"
    assert outcome["cssClass"] != "try-status-ok"
    assert "401" in outcome["label"]
    assert "สิทธิ์" in outcome["label"] or "credential" in outcome["label"]


def test_403_hints_credential_too() -> None:
    outcome = describe({"ok": True, "response": {"statusCode": 403, "elapsedMs": 8.0}})
    assert outcome["kind"] == "http_error"
    assert "403" in outcome["label"]


def test_404_hints_endpoint() -> None:
    outcome = describe({"ok": True, "response": {"statusCode": 404, "elapsedMs": 8.0}})
    assert outcome["kind"] == "http_error"
    assert "endpoint" in outcome["label"] or "resource" in outcome["label"]


def test_429_hints_rate_limit() -> None:
    outcome = describe({"ok": True, "response": {"statusCode": 429, "elapsedMs": 8.0}})
    assert outcome["kind"] == "http_error"
    assert "จำกัดอัตรา" in outcome["label"] or "rate limit" in outcome["label"]


def test_500_hints_server_problem() -> None:
    outcome = describe({"ok": True, "response": {"statusCode": 500, "elapsedMs": 8.0}})
    assert outcome["kind"] == "http_error"
    assert outcome["cssClass"] == "try-status-warn"
    assert "500" in outcome["label"]


def test_401_and_200_render_with_different_css_classes() -> None:
    ok = describe({"ok": True, "response": {"statusCode": 200, "elapsedMs": 1}})
    unauthorized = describe({"ok": True, "response": {"statusCode": 401, "elapsedMs": 1}})
    assert ok["cssClass"] != unauthorized["cssClass"]


# --------------------------------------------- ระบบบล็อกก่อนยิง vs เชื่อมต่อไม่ได้ --


def test_ssrf_block_is_not_described_as_upstream_answered() -> None:
    outcome = describe(
        {"ok": False, "reason": "internal_ip", "error": "ปลายทางเป็น IP ภายใน/ไม่ปลอดภัย"}
    )
    assert outcome["kind"] == "blocked"
    assert "ปลายทางตอบ" not in outcome["label"]
    assert "internal_ip" in outcome["label"]


def test_connection_failure_is_a_distinct_kind_from_policy_block() -> None:
    blocked = describe(
        {"ok": False, "reason": "domain_not_in_allowlist", "error": "โดเมนไม่อยู่ใน allowlist"}
    )
    connection_failed = describe(
        {"ok": False, "reason": "request_failed", "error": "ไม่สามารถเชื่อมต่อปลายทางได้"}
    )
    assert blocked["kind"] == "blocked"
    assert connection_failed["kind"] == "connection_failed"
    assert blocked["label"] != connection_failed["label"]


def test_redirect_and_size_limit_reasons_still_shown_correctly() -> None:
    redirect = describe(
        {"ok": False, "reason": "redirect_blocked", "error": "ปลายทางพยายาม redirect"}
    )
    too_large = describe(
        {"ok": False, "reason": "response_too_large", "error": "response ใหญ่เกินเพดาน"}
    )
    assert redirect["kind"] == "after_send_failed"
    assert "redirect_blocked" in redirect["label"]
    assert "หลังเริ่มส่ง" in redirect["label"]
    assert "side effect" in redirect["note"]
    assert too_large["kind"] == "after_send_failed"
    assert "response_too_large" in too_large["label"]
    assert "หลังเริ่มส่ง" in too_large["label"]


def test_unknown_failure_is_not_mislabeled_as_a_policy_block() -> None:
    outcome = describe({"ok": False, "reason": "missing_secret", "error": "ไม่พบ credential"})
    assert outcome["kind"] == "pre_send_error"
    assert "ระบบบล็อกก่อนส่งคำขอ" not in outcome["label"]


# --------------------------------------------------- ต่อสาย admin.js ใช้ผลนี้จริง --


def test_admin_js_uses_describe_try_outcome_for_status_line() -> None:
    js = ADMIN_JS.read_text()
    assert "describeTryOutcome" in js
    # ต้องไม่เหลือรูปแบบเดิมที่แสดง "สำเร็จ" ทุกกรณีโดยไม่ตรวจ status code
    assert '"สำเร็จ · HTTP "' not in js


def test_admin_js_clears_new_status_classes_between_fires() -> None:
    """กันสถานะเก่าค้าง เช่น กด "ยิงจริง" ซ้ำจาก 401 แล้วครั้งถัดไปเป็น 200"""
    js = ADMIN_JS.read_text()
    assert "try-status-warn" in js
    assert "try-status-note" in js


def test_try_fire_button_cannot_submit_tool_form() -> None:
    """The dynamically-created production button must stay a non-submit control."""
    js = ADMIN_JS.read_text()
    assert 'fireBtn.type = "button"' in js
    assert "event.preventDefault()" in js
