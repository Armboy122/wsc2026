"""การประกาศ capability ของแต่ละช่องทางตาม CONTRACTS-V2.md §5.4"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    """คุณสมบัติและการรองรับของแต่ละช่องทาง

    agent ไม่เคยอ่าน capability — adapter อ่านของตัวเองเพื่อ degrade ตาม §5.4
    """

    buttons: bool
    editable_message: bool
    rich_layout: bool
    max_text_length: int | None
    max_buttons: int | None


# ค่าที่ตรึงไว้ตามตาราง CONTRACTS-V2.md §5.4
CHANNEL_CAPABILITIES: dict[str, ChannelCapabilities] = {
    "web": ChannelCapabilities(
        buttons=True,
        editable_message=True,
        rich_layout=False,
        max_text_length=None,
        max_buttons=None,
    ),
    "line": ChannelCapabilities(
        buttons=True,
        editable_message=False,
        rich_layout=True,
        max_text_length=1900,
        max_buttons=13,
    ),
    "telegram": ChannelCapabilities(
        buttons=True,
        editable_message=True,
        rich_layout=False,
        max_text_length=4096,
        max_buttons=100,
    ),
    "voice": ChannelCapabilities(
        buttons=False,
        editable_message=False,
        rich_layout=False,
        max_text_length=None,
        max_buttons=None,
    ),
    "api": ChannelCapabilities(
        buttons=False,
        editable_message=False,
        rich_layout=False,
        max_text_length=None,
        max_buttons=None,
    ),
}


def get_channel_capabilities(channel: str) -> ChannelCapabilities:
    """ดึง capability ของ channel ที่ระบุ (fallback เป็นค่าปลอดภัยถ้าไม่รู้จัก)"""
    norm = channel.lower().strip()
    if norm in CHANNEL_CAPABILITIES:
        return CHANNEL_CAPABILITIES[norm]
    return ChannelCapabilities(
        buttons=False,
        editable_message=False,
        rich_layout=False,
        max_text_length=None,
        max_buttons=None,
    )
