"""การจัดรูปแบบข้อความและการ degrade สำหรับ channel ตาม CONTRACTS-V2.md §5.4, §5.5"""

from __future__ import annotations

from typing import Any, Sequence

from app.channel.capabilities import ChannelCapabilities
from app.contracts import Action

SIMULATION_NOTICE = "ℹ️ รายการนี้ทำงานบนระบบจำลองเพื่อการสาธิต (ไม่ใช่ระบบ PEA จริง)"
WELCOME_TEXT = "สวัสดีครับ ผมคือ น้องทัชชี่ พร้อมให้บริการแล้วครับ📌"

_DEFAULT_LABEL_LIMIT = 20


def truncate_button_label(text: str, limit: int = _DEFAULT_LABEL_LIMIT) -> str:
    """ตัดป้ายปุ่มให้อยู่ในเพดานตัวอักษร"""
    if len(text) <= limit:
        return text
    return text[:limit - 1] + "…"


def split_text(text: str, limit: int | None = None) -> list[str]:
    """ตัดข้อความยาวให้อยู่ในเพดานต่อข้อความตามสัญญา §5.5

    - หากไม่กำหนดเพดาน (None หรือ <= 0) จะไม่ตัดข้อความ (เช่น Web, API)
    - พยายามตัดที่ขอบเขตบรรทัดก่อน ถ้าบรรทัดเดียวยาวเกินจึงตัดที่ช่องว่างหรือความยาว
    """
    if not text:
        return []
    if limit is None or limit <= 0 or len(text) <= limit:
        return [text]

    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            break_point = line.rfind(" ", 0, limit)
            if break_point > 0:
                parts.append(line[:break_point])
                line = line[break_point + 1:]
            else:
                parts.append(line[:limit])
                line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                parts.append(current)
            current = line
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def format_citations_text(citations: Sequence[dict[str, Any] | Any]) -> str:
    """สร้างข้อความสรุปรายการเอกสารอ้างอิง"""
    lines = ["แหล่งอ้างอิง:"]
    for citation in citations:
        if isinstance(citation, dict):
            title = str(citation.get("title") or "เอกสาร")
            page = citation.get("page")
        else:
            title = str(getattr(citation, "title", None) or "เอกสาร")
            page = getattr(citation, "page", None)
        lines.append(f"• {title}" + (f" (หน้า {page})" if page else ""))
    return "\n".join(lines)


def extract_citation_links(
    citations: Sequence[dict[str, Any] | Any],
    max_links: int | None = None,
) -> list[tuple[str, str]]:
    """ดึงรายการ (title, http_url) จาก citations เพื่อสร้างปุ่มลิงก์"""
    results: list[tuple[str, str]] = []
    for citation in citations:
        if isinstance(citation, dict):
            title = str(citation.get("title") or "เอกสาร")
            uri = str(citation.get("uri") or "")
        else:
            title = str(getattr(citation, "title", None) or "เอกสาร")
            uri = str(getattr(citation, "uri", None) or "")
        if uri.startswith(("http://", "https://")):
            results.append((title, uri))
            if max_links is not None and len(results) >= max_links:
                break
    return results


def degrade_for_channel(
    message: str,
    actions: Sequence[Action] = (),
    capabilities: ChannelCapabilities | None = None,
    pending_action_id: str | None = None,
    prompt_id: str | None = None,
) -> tuple[list[str], list[Action]]:
    """ปรับรูปข้อความและ actions ตามความสามารถของช่องทาง (CONTRACTS-V2.md §5.4)

    - หากช่องทางไม่รองรับ buttons (เช่น API, Voice): degrade แปลงตัวเลือกเป็นข้อความพร้อมรหัส id
    - หากช่องทางมีเพดาน max_text_length: ตัดข้อความเป็นท่อนตามสัญญา §5.5
    - หากช่องทางมีเพดาน max_buttons: จำกัดจำนวนปุ่ม
    """
    if capabilities is None:
        return [message], list(actions)

    split_limit = capabilities.max_text_length

    if not capabilities.buttons:
        # ช่องทางไม่มีปุ่ม: degrade เป็นข้อความ + id
        degraded_lines: list[str] = [message]
        extra_lines: list[str] = []
        if pending_action_id:
            extra_lines.append(f"รหัสรายการที่รอดำเนินการ: {pending_action_id}")
        if prompt_id:
            extra_lines.append(f"รหัสขั้นตอน: {prompt_id}")
        if actions:
            extra_lines.append("ตัวเลือกการดำเนินการ:")
            for idx, act in enumerate(actions, start=1):
                extra_lines.append(f"[{idx}] {act.label} (ส่ง: {act.value})")
        if extra_lines:
            degraded_lines.append("\n" + "\n".join(extra_lines))
        full_text = "\n".join(degraded_lines)
        return split_text(full_text, split_limit), []

    # ช่องทางมีปุ่ม
    final_actions = list(actions)
    if capabilities.max_buttons is not None:
        final_actions = final_actions[:capabilities.max_buttons]
    return split_text(message, split_limit), final_actions
