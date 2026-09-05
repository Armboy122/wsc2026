"""Regression test: หน้าล็อกอินต้องถูกซ่อนได้จริงเมื่อล็อกอินสำเร็จ

บั๊กที่เจอตอนซ้อมเดโม: ล็อกอินได้ HTTP 200 แต่หน้าจอยังค้างอยู่ที่ฟอร์มล็อกอิน
กด "เข้าสู่ระบบ" ซ้ำได้เรื่อย ๆ (log เห็น admin_login_succeeded ซ้ำหลายรอบ)

สาเหตุ: ``showApp()`` ตั้ง ``views.loginView.hidden = true`` ซึ่งพึ่งกฎ default
ของเบราว์เซอร์ ``[hidden] { display: none }`` (specificity 0-0-1) แต่ ``#login-view``
มี ``class="auth-wrap"`` ที่ประกาศ ``display: grid`` (specificity 0-1-0) จึงทับกฎ
default ทำให้ attribute ``hidden`` ไม่มีผลกับ element นั้น

เทสนี้ล็อกสองอย่างไว้:
1. ทุก element ที่ JS สั่งซ่อน/แสดงผ่าน attribute ``hidden`` ต้องถูกซ่อนได้จริง
   แม้จะมี class ที่ประกาศ ``display`` ของตัวเอง
2. ``admin.css`` ต้องมีกฎที่บังคับ ``[hidden]`` ให้ชนะ class selector
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "web" / "admin.html"
CSS = ROOT / "web" / "admin.css"

# element ที่ JS สลับการแสดงผลด้วย attribute hidden ในเส้นทางล็อกอิน
TOGGLED_VIEW_IDS = ("login-view", "app-view")


def _class_names_of(element_id: str, html: str) -> list[str]:
    """คืนรายการ class ของ element ที่มี id ที่ระบุ (ลำดับ attribute ใดก็ได้)"""
    tag = re.search(rf"<[^>]*\bid=\"{re.escape(element_id)}\"[^>]*>", html)
    assert tag is not None, f"ไม่พบ element id={element_id} ใน admin.html"
    classes = re.search(r'\bclass="([^"]*)"', tag.group(0))
    return classes.group(1).split() if classes else []


def test_hidden_attribute_is_forced_to_win_over_class_display_rules() -> None:
    """admin.css ต้องบังคับ [hidden] ให้ชนะ class ที่ประกาศ display เอง"""
    css = CSS.read_text(encoding="utf-8")
    forced_hidden = re.search(
        r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important", css, re.DOTALL
    )
    assert forced_hidden is not None, (
        "admin.css ต้องมีกฎ [hidden] { display: none !important } "
        "ไม่งั้น class อย่าง .auth-wrap { display: grid } จะทับ attribute hidden "
        "ทำให้หน้าล็อกอินค้างทับหน้าแอดมินหลังล็อกอินสำเร็จ"
    )


def test_every_toggled_view_can_actually_be_hidden() -> None:
    """view ที่ JS ซ่อนด้วย hidden ต้องไม่ถูก class ของตัวเองบังคับให้แสดงผล"""
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    forced_hidden = bool(
        re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important", css, re.DOTALL)
    )

    for view_id in TOGGLED_VIEW_IDS:
        for class_name in _class_names_of(view_id, html):
            declares_display = re.search(
                rf"\.{re.escape(class_name)}\s*\{{[^}}]*display\s*:", css, re.DOTALL
            )
            if declares_display and not forced_hidden:
                raise AssertionError(
                    f"#{view_id} ใช้ class .{class_name} ที่ประกาศ display เอง "
                    "ซึ่งมี specificity สูงกว่ากฎ [hidden] ของเบราว์เซอร์ "
                    "attribute hidden จึงไม่มีผล — ต้องมีกฎบังคับใน admin.css"
                )


def test_login_and_app_views_start_hidden_in_markup() -> None:
    """ทั้งสอง view ต้องเริ่มต้นแบบซ่อน แล้วให้ init() เป็นคนตัดสินว่าจะแสดงอันไหน"""
    html = HTML.read_text(encoding="utf-8")
    for view_id in TOGGLED_VIEW_IDS:
        tag = re.search(rf"<[^>]*\bid=\"{re.escape(view_id)}\"[^>]*>", html)
        assert tag is not None, f"ไม่พบ element id={view_id}"
        assert re.search(r"\bhidden\b", tag.group(0)), (
            f"#{view_id} ต้องมี attribute hidden ตั้งแต่ใน markup "
            "เพื่อไม่ให้เห็นหน้าจอกะพริบก่อน init() ตรวจ session เสร็จ"
        )
