"""Deterministic, bounded PEA residential estimate (no provider or network access)."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

RATE_SOURCE = "PEA_Electricity_Tariff_SEP_2026"
FT_SOURCE = "PEA_Ft_SEP_DEC_2026"
D = Decimal

@dataclass(frozen=True)
class BillResult:
    status: str
    reason: str | None = None
    usage: Decimal | None = None
    energy: Decimal | None = None
    service: Decimal | None = None
    ft: Decimal | None = None
    subtotal_before_vat: Decimal | None = None
    display_total: Decimal | None = None
    vat: Decimal | None = None
    final_total: Decimal | None = None
    citations: tuple[str, ...] = (RATE_SOURCE, FT_SOURCE)


def _finite_nonnegative(value: Decimal, name: str) -> None:
    if not value.is_finite() or value < 0 or value > D("1000000"):
        raise ValueError(f"{name} must be finite, nonnegative, and bounded")


def calculate_residential_bill(*, usage: Decimal | str, month: int, year: int,
                               subtype: str = "1.1.2") -> BillResult:
    """Calculate only explicitly supported normal residential 1.1.2, before VAT."""
    try:
        units = D(str(usage))
    except Exception as exc:
        raise ValueError("usage must be Decimal-compatible") from exc
    _finite_nonnegative(units, "usage")
    if isinstance(usage, bool):
        raise ValueError("usage must be Decimal-compatible")
    if month < 1 or month > 12 or year not in (2569, 2026):
        return BillResult("unavailable", reason="Tariff period is not verified")
    if subtype != "1.1.2":
        return BillResult("unavailable", reason="Only confirmed residential normal 1.1.2 is supported")
    # The approved evidence covers September through December 2569 only.
    if year == 2026 and month < 9 or year == 2569 and month < 9:
        return BillResult("unavailable", reason="Tariff period is not verified")
    energy = min(units, D("200"))*D("3.0000")
    energy += max(min(units-D("200"), D("200")), D("0"))*D("4.1584")
    energy += max(units-D("400"), D("0"))*D("4.3583")
    service = D("24.62")
    ft = units * D("0.1623")
    subtotal = energy + service + ft
    if month == 9:
        vat = subtotal * D("0.07")
        total = subtotal + vat
        return BillResult("calculated", usage=units, energy=energy, service=service, ft=ft,
                          subtotal_before_vat=subtotal, vat=vat,
                          final_total=total,
                          display_total=total.quantize(D("0.01"), rounding=ROUND_HALF_UP),
                          reason="September combined VAT estimate: 6.3% national + 0.7% local")
    return BillResult("partial", usage=units, energy=energy, service=service, ft=ft,
                      subtotal_before_vat=subtotal,
                      display_total=subtotal.quantize(D("0.01"), rounding=ROUND_HALF_UP),
                      reason="VAT/final payable is unavailable for this period")
