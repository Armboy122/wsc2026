"""การแปลงและการจัดการ Action สำหรับทุก channel ตาม CONTRACTS-V2.md §5.2, §5.3"""

from __future__ import annotations

import secrets
import threading
import urllib.parse
from typing import Any, Sequence

from app.contracts import Action, ChoicePrompt, PendingAction

ACTION_CONFIRM = "action=confirm"
ACTION_REJECT = "action=reject"
ACTION_NEW_CHAT = "action=new_chat"
ACTION_INTENT_PREFIX = "action=intent&text="

_MAX_VALUE_BYTES = 64
_MAX_CHOICE_CACHE = 2000

_choice_lock = threading.Lock()
_CHOICE_REGISTRY: dict[str, tuple[str, str]] = {}


def register_choice(prompt_id: str, value: str) -> str:
    """ลงทะเบียน choice ใน mapping ฝั่ง server เพื่อให้ได้ callback value สั้น ≤64 bytes

    รับประกันว่าจะไม่ตัดทอน prompt_id และคงค่า value ไว้ครบถ้วน
    (รวมถึงข้อความภาษาไทยขนาดยาว และอักขระพิเศษ เช่น &, +)
    """
    token = secrets.token_hex(8)
    with _choice_lock:
        if len(_CHOICE_REGISTRY) >= _MAX_CHOICE_CACHE:
            keys_to_remove = list(_CHOICE_REGISTRY.keys())[: _MAX_CHOICE_CACHE // 2]
            for k in keys_to_remove:
                _CHOICE_REGISTRY.pop(k, None)
        _CHOICE_REGISTRY[token] = (prompt_id, value)
    return f"pick:{token}"


def lookup_choice(token: str) -> tuple[str, str] | None:
    """ค้นหา (prompt_id, value) จาก token ที่ลงทะเบียนไว้"""
    with _choice_lock:
        return _CHOICE_REGISTRY.get(token)


def format_actions(
    pending_action: PendingAction | dict[str, Any] | None = None,
    choice_prompt: ChoicePrompt | dict[str, Any] | None = None,
) -> tuple[Action, ...]:
    """helper กลางแปลง pendingAction และ choicePrompt เป็น Action[]

    ตาม CONTRACTS-V2.md §5.3: แยกที่สัญญา แต่รวมที่การแปลง
    ทุก action ที่ได้จาก helper นี้เป็น singleUse: true
    """
    actions: list[Action] = []

    if pending_action is not None:
        actions.append(
            Action(
                label="ยืนยัน",
                value=ACTION_CONFIRM,
                kind="confirm",
                single_use=True,
            )
        )
        actions.append(
            Action(
                label="ยกเลิก",
                value=ACTION_REJECT,
                kind="reject",
                single_use=True,
            )
        )

    if choice_prompt is not None:
        if isinstance(choice_prompt, dict):
            prompt_id = str(choice_prompt.get("promptId") or choice_prompt.get("prompt_id") or "")
            raw_options = choice_prompt.get("options") or ()
        else:
            prompt_id = str(choice_prompt.prompt_id or "")
            raw_options = choice_prompt.options or ()

        for opt in raw_options:
            if isinstance(opt, dict):
                opt_label = str(opt.get("label") or opt.get("value") or "")
                opt_value = str(opt.get("value") or "")
            else:
                opt_label = str(opt.label or opt.value or "")
                opt_value = str(opt.value or "")

            val = _build_pick_value(prompt_id, opt_value)
            if val:
                actions.append(
                    Action(
                        label=opt_label,
                        value=val,
                        kind="pick",
                        single_use=True,
                    )
                )

    return tuple(actions)


def _build_pick_value(prompt_id: str, value: str) -> str:
    """สร้างค่า callback สำหรับการเลือก choice ให้ยาวไม่เกิน 64 bytes โดยไม่ตัดทอน semantic data"""
    return register_choice(prompt_id, value)


def parse_action_callback(data: str) -> dict[str, Any]:
    """แยกวิเคราะห์ callback_data หรือ postback data กลาง"""
    raw = (data or "").strip()
    if raw == ACTION_CONFIRM:
        return {"action": "confirm"}
    if raw == ACTION_REJECT:
        return {"action": "reject"}
    if raw == ACTION_NEW_CHAT:
        return {"action": "new_chat"}
    if raw.startswith(ACTION_INTENT_PREFIX):
        intent_text = urllib.parse.unquote(raw[len(ACTION_INTENT_PREFIX):]).strip()
        return {"action": "intent", "text": intent_text}

    if raw.startswith("pick:"):
        token = raw[len("pick:"):].strip()
        registered = lookup_choice(token)
        if registered is not None:
            return {"action": "pick", "prompt_id": registered[0], "value": registered[1]}
        parts = raw.split(":", 2)
        if len(parts) == 3 and parts[1]:
            return {"action": "pick", "prompt_id": parts[1], "value": parts[2]}
        return {"action": "pick", "prompt_id": None, "value": token}

    if raw.startswith("action=pick&"):
        parsed = urllib.parse.parse_qs(raw[len("action=pick&"):])
        prompt_id = parsed.get("p", [None])[0]
        value = parsed.get("v", [""])[0]
        return {"action": "pick", "prompt_id": prompt_id, "value": value}

    return {"action": "unknown", "data": raw}
