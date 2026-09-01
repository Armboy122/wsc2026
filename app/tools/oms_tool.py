"""เครื่องมือ OMS REST ภายนอกที่เก็บรายการเตรียมไว้ในเครื่องก่อนส่งจริง"""
from __future__ import annotations

from typing import Any

import httpx

from app.backends import BackendError
from app.contracts import ToolAction, ToolErrorCode, ToolName
from app.tools._base import SimulatedTool


class OmsTool(SimulatedTool):
    """เรียกใช้สัญญา OMS คงที่ โดยรายการเตรียมจะไม่เรียก OMS"""

    name = ToolName.OMS

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 5,
        *,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            transport=transport,
        )
        self._drafts: dict[str, tuple[ToolAction, dict[str, Any]]] = {}

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            headers = {"X-API-Key": self.api_key} if self.api_key else None
            response = self._client.request(method, path, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise BackendError(ToolErrorCode.UNAVAILABLE, "ไม่สามารถเชื่อมต่อ OMS ได้") from exc
        if response.status_code in (400,):
            raise BackendError(ToolErrorCode.INVALID_INPUT, "ข้อมูลแจ้งเหตุไม่ถูกต้อง")
        if response.status_code == 404:
            raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบหมายเลขผู้ใช้ไฟในระบบ OMS")
        if response.status_code == 409:
            raise BackendError(ToolErrorCode.CONFLICT, "พบเหตุการณ์ที่เกี่ยวข้องใน OMS แล้ว")
        if response.status_code >= 500:
            raise BackendError(ToolErrorCode.UNAVAILABLE, "OMS ไม่พร้อมให้บริการ")
        if response.status_code != (200 if method == "GET" else 201):
            raise BackendError(ToolErrorCode.UNAVAILABLE, "OMS ไม่พร้อมให้บริการ")
        try:
            value = response.json()
        except (ValueError, TypeError) as exc:
            raise BackendError(ToolErrorCode.INTERNAL, "OMS ตอบกลับข้อมูลไม่ถูกต้อง") from exc
        if not isinstance(value, dict):
            raise BackendError(ToolErrorCode.INTERNAL, "OMS ตอบกลับข้อมูลไม่ถูกต้อง")
        return value

    def _run(self, action: ToolAction, input_model: Any) -> dict[str, Any]:
        if action is ToolAction.OMS_GET_OUTAGE_BY_CA:
            return self._request("GET", f"outages/by-ca/{input_model.ca_number}")
        if action is ToolAction.OMS_PREPARE_OUTAGE_WITH_CA:
            payload = input_model.model_dump(by_alias=True, mode="json")
            key = payload.pop("idempotencyKey")
            self._drafts[key] = (action, payload)
            return {"summary": "เตรียมแจ้งเหตุไฟฟ้าขัดข้องสำหรับหมายเลขผู้ใช้ไฟแล้ว"}
        if action is ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE:
            payload = input_model.model_dump(by_alias=True, mode="json")
            key = payload.pop("idempotencyKey")
            self._drafts[key] = (action, payload)
            return {"summary": "เตรียมแจ้งเหตุไฟฟ้าขัดข้องแบบไม่ทราบหมายเลขผู้ใช้ไฟแล้ว"}
        if action in (ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA, ToolAction.OMS_SUBMIT_ANONYMOUS_OUTAGE):
            draft = self._drafts.get(input_model.idempotency_key)
            if draft is None:
                raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบรายการที่เตรียมไว้")
            prepare_action, payload = draft
            expected = (
                ToolAction.OMS_PREPARE_OUTAGE_WITH_CA
                if action is ToolAction.OMS_SUBMIT_OUTAGE_WITH_CA
                else ToolAction.OMS_PREPARE_ANONYMOUS_OUTAGE
            )
            if prepare_action is not expected:
                raise BackendError(ToolErrorCode.INVALID_INPUT, "ประเภทรายการไม่ตรงกัน")
            path = "outages" if expected is ToolAction.OMS_PREPARE_OUTAGE_WITH_CA else "outages/anonymous"
            result = self._request("POST", path, payload)
            del self._drafts[input_model.idempotency_key]
            return result
        raise ValueError(f"ไม่มีการจัดการการกระทำ {action.value}")

    def reset(self) -> None:
        self._drafts.clear()

    def close(self) -> None:
        self._client.close()
