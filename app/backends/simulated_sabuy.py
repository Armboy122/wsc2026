"""backend Sabuy (ชำระค่าไฟ) ในหน่วยความจำแบบกำหนดผลลัพธ์ได้

อ่านบัญชี fixture แบบคงที่จาก ``data/mock/sabuy_accounts.json`` และบันทึกการชำระเงินจำลอง
ไว้ในสถานะภายใน process โดยไม่มีการเรียก PEA ระบบจริง
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.backends import BackendError, load_mock_json
from app.contracts import PaymentMethod, ToolErrorCode


class SimulatedSabuyBackend:
    """backend บัญชีและการชำระเงิน Sabuy แบบจำลองที่มีสถานะภายใน process ซึ่งรีเซ็ตได้"""

    def __init__(self) -> None:
        rows = load_mock_json("sabuy_accounts.json")
        self._accounts: dict[str, dict[str, Any]] = {row["accountRef"]: row for row in rows}
        self._prepared: dict[str, dict[str, Any]] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def reset(self) -> None:
        """ล้างฉบับร่างที่เตรียมไว้และใบเสร็จที่ส่งแล้ว เพื่อคืนสถานะเริ่มต้น"""
        self._prepared.clear()
        self._receipts.clear()
        self._seq = 0

    def get_account_summary(self, account_ref: str) -> dict[str, Any]:
        """ส่งคืนข้อมูลสรุป fixture สำหรับ ``account_ref`` (อ่านอย่างเดียว)"""
        account = self._accounts.get(account_ref)
        if account is None:
            raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบบัญชี")
        return {
            "accountRef": account["accountRef"],
            "customerDisplayName": account["customerDisplayName"],
            "outstandingBalanceThb": account["outstandingBalanceThb"],
            "dueDate": account["dueDate"],
            "paymentStatus": account["paymentStatus"],
        }

    def prepare_payment(
        self,
        account_ref: str,
        amount_thb: Decimal,
        payment_method: PaymentMethod,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """ตรวจสอบและจัดเตรียมฉบับร่างการชำระเงิน โดยยังไม่บันทึกการชำระเงินจำลอง"""
        if account_ref not in self._accounts:
            raise BackendError(ToolErrorCode.NOT_FOUND, "ไม่พบบัญชี")
        amount = str(amount_thb)
        self._prepared[idempotency_key] = {
            "accountRef": account_ref,
            "amountThb": amount,
            "paymentMethod": payment_method.value,
        }
        summary = (
            f"เตรียมชำระเงิน {amount} THB ให้บัญชี {account_ref} "
            f"ด้วย {payment_method.value}"
        )
        return {
            "accountRef": account_ref,
            "amountThb": amount,
            "paymentMethod": payment_method.value,
            "summary": summary,
        }

    def submit_payment(self, pending_action_id: UUID, idempotency_key: str) -> dict[str, Any]:
        """บันทึกการชำระเงินที่จัดเตรียมไว้เพียงหนึ่งครั้ง โดยตัดรายการซ้ำด้วย idempotency key"""
        existing = self._receipts.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        prepared = self._prepared.get(idempotency_key)
        if prepared is None:
            raise BackendError(
                ToolErrorCode.NOT_FOUND,
                "ไม่มีการชำระเงินที่จัดเตรียมไว้สำหรับ idempotency key นี้",
            )
        self._seq += 1
        receipt = {
            "receiptId": f"SIM-RCPT-{self._seq:06d}",
            "accountRef": prepared["accountRef"],
            "amountThb": prepared["amountThb"],
            "status": "accepted",
        }
        self._receipts[idempotency_key] = receipt
        return dict(receipt)


default_backend = SimulatedSabuyBackend()
