"""VOC tool with a local prepare gate and optional REST gateway transport."""

from __future__ import annotations

from typing import Any

import httpx

from app.backends import BackendError
from app.backends.simulated_voc import SimulatedVocBackend, default_backend
from app.contracts import ToolAction, ToolErrorCode, ToolName
from app.tools._base import SimulatedTool


_CATEGORY_TO_JOURNEY = {
    "power_quality": "POWER_QUALITY",
    "service": "SERVICE_ISSUE",
    "compliment": "PRAISE",
    "tip_off": "TIP_OFF",
    "operations": "STAKEHOLDER_ISSUE",
    "stakeholder_feedback": "STAKEHOLDER_FEEDBACK",
}
_JOURNEY_TO_CATEGORY = {value: key for key, value in _CATEGORY_TO_JOURNEY.items()}


class VocTool(SimulatedTool):
    """VOC semantic facade.

    ``VocTool()`` keeps the legacy in-memory backend for existing demo callers.
    Supplying ``base_url`` enables the gateway transport used by the plugin.  A
    prepare call never performs HTTP; the canonical gateway request must be
    supplied explicitly as ``externalPayload`` to prevent guessed taxonomy,
    location, or consent values.
    """

    name = ToolName.VOC

    def __init__(
        self,
        backend: SimulatedVocBackend | None = None,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 5.0,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.backend = backend if backend is not None else default_backend
        self._api_mode = base_url is not None
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.api_key = api_key
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_seconds, transport=transport) if self._api_mode else None
        self._drafts: dict[str, dict[str, Any]] = {}
        # catalog เป็นข้อมูลอ้างอิงที่เปลี่ยนช้าและมี catalogVersion กำกับ
        # cache ไว้ต่อ process เพื่อไม่ยิงซ้ำทุกขั้นของการถามตอบ
        self._catalog_cache: dict[str, Any] | None = None

    def get_catalog(self) -> dict[str, Any]:
        """คืน catalog ดิบสำหรับขับลำดับคำถาม intake โดยไม่ให้โมเดลเดารหัสเอง"""
        if not self._api_mode:
            raise BackendError(ToolErrorCode.UNAVAILABLE, "ต้องเชื่อมต่อระบบ VOC เพื่ออ่าน catalog")
        if self._catalog_cache is None:
            self._catalog_cache = self._request("GET", "catalog")
        return self._catalog_cache

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, *, idempotency_key: str | None = None) -> dict[str, Any]:
        assert self._client is not None
        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self._client.request(method, path, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise BackendError(ToolErrorCode.UNAVAILABLE, "ไม่สามารถเชื่อมต่อระบบ VOC ได้") from exc
        if response.status_code == 400:
            raise BackendError(ToolErrorCode.INVALID_INPUT, "ข้อมูล VOC ไม่ถูกต้อง")
        if response.status_code == 404:
            raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบเคส VOC สำหรับข้อมูลติดตามที่ระบุ")
        if response.status_code == 409:
            raise BackendError(ToolErrorCode.CONFLICT, "คีย์รายการ VOC ถูกใช้กับข้อมูลอื่นแล้ว")
        if response.status_code >= 500:
            raise BackendError(ToolErrorCode.UNAVAILABLE, "ระบบ VOC ไม่พร้อมให้บริการ")
        if response.status_code not in (200, 201):
            raise BackendError(ToolErrorCode.INTERNAL, "ระบบ VOC ตอบกลับไม่ถูกต้อง")
        try:
            value = response.json()
        except (ValueError, TypeError) as exc:
            raise BackendError(ToolErrorCode.INTERNAL, "ระบบ VOC ตอบกลับข้อมูลไม่ถูกต้อง") from exc
        if not isinstance(value, dict):
            raise BackendError(ToolErrorCode.INTERNAL, "ระบบ VOC ตอบกลับข้อมูลไม่ถูกต้อง")
        return value

    def _run(self, action: ToolAction, input_model: Any) -> dict[str, Any]:
        if not self._api_mode:
            return self._run_simulated(action, input_model)
        if action is ToolAction.VOC_LIST_CATEGORIES:
            catalog = self._request("GET", "catalog")
            journeys = catalog.get("journeys")
            if not isinstance(journeys, list):
                raise BackendError(ToolErrorCode.INTERNAL, "ระบบ VOC ส่ง catalog ไม่ถูกต้อง")
            categories = [
                {"code": _JOURNEY_TO_CATEGORY.get(item.get("code", ""), ""), "label": item.get("label", "")}
                for item in journeys if isinstance(item, dict) and item.get("code") in _JOURNEY_TO_CATEGORY
            ]
            if len(categories) != 6 or any(not item["code"] or not item["label"] for item in categories):
                raise BackendError(ToolErrorCode.INTERNAL, "ระบบ VOC ส่ง catalog ไม่ครบถ้วน")
            return {"categories": categories}
        if action is ToolAction.VOC_PREPARE_CASE:
            if not input_model.external_payload:
                raise BackendError(ToolErrorCode.INVALID_INPUT, "ต้องระบุข้อมูล VOC ตาม catalog ให้ครบก่อนเตรียมเรื่อง")
            self._drafts[input_model.idempotency_key] = input_model.external_payload.model_dump(by_alias=True, exclude_none=True, mode="json")
            return {"category": input_model.category, "subject": input_model.subject, "summary": "เตรียมเรื่อง VOC แล้ว กรุณาตรวจสอบและยืนยันก่อนส่ง"}
        if action is ToolAction.VOC_SUBMIT_CASE:
            payload = self._drafts.get(input_model.idempotency_key)
            if payload is None:
                raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบรายการ VOC ที่เตรียมไว้")
            result = self._request("POST", "cases", payload, idempotency_key=input_model.idempotency_key)
            self._drafts.pop(input_model.idempotency_key, None)
            return {
                "caseId": result.get("caseId", ""),
                "vocId": result.get("vocNumber", ""),
                "trackingKey": result.get("keyCode", ""),
                "status": "submitted",
                "category": _JOURNEY_TO_CATEGORY.get(result.get("journeyCode", ""), "service"),
            }
        if action is ToolAction.VOC_GET_CASE:
            result = self._request("POST", "cases/lookup", {"vocNumber": input_model.voc_id, "keyCode": input_model.tracking_key})
            case = result.get("case")
            if not isinstance(case, dict):
                raise BackendError(ToolErrorCode.INTERNAL, "ระบบ VOC ส่งรายละเอียดเคสไม่ถูกต้อง")
            return {
                "vocId": case.get("vocNumber", ""),
                "status": str(case.get("status", "")).lower(),
                "category": _JOURNEY_TO_CATEGORY.get(case.get("journeyCode", ""), "service"),
                "createdAt": case.get("createdAt"),
                "updatedAt": case.get("updatedAt"),
            }
        raise ValueError(f"ไม่มีการจัดการการกระทำ {action.value}")

    def _run_simulated(self, action: ToolAction, input_model: Any) -> dict[str, Any]:
        if action is ToolAction.VOC_LIST_CATEGORIES:
            return self.backend.list_categories()
        if action is ToolAction.VOC_PREPARE_CASE:
            return self.backend.prepare_case(input_model.category, input_model.subject, input_model.detail, input_model.contact_name, input_model.contact_phone, input_model.location, input_model.contact_channel, input_model.idempotency_key)
        if action is ToolAction.VOC_SUBMIT_CASE:
            return self.backend.submit_case(input_model.pending_action_id, input_model.idempotency_key)
        if action is ToolAction.VOC_GET_CASE:
            return self.backend.get_case(input_model.voc_id, input_model.tracking_key)
        raise ValueError(f"ไม่มีการจัดการการกระทำ {action.value}")

    def reset(self) -> None:
        self._drafts.clear()
        self._catalog_cache = None
        if not self._api_mode:
            self.backend.reset()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
