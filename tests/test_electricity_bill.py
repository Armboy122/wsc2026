from decimal import Decimal
import pytest
from app.backends.electricity_bill import calculate_residential_bill


def test_september_966_calculated_with_combined_vat():
    r = calculate_residential_bill(usage=Decimal("966"), month=9, year=2569)
    assert r.status == "calculated"
    assert r.subtotal_before_vat == Decimal("4079.8796")
    assert r.vat == Decimal("285.591572")
    assert r.final_total == Decimal("4365.471172")
    assert r.display_total == Decimal("4365.47")

@pytest.mark.parametrize("units, expected_energy", [
    ("0", "0"), ("199.999", "599.9970"), ("200", "600.0000"),
    ("200.001", "600.0041584"), ("399.999", "1431.675?"), ("400", "1431.6800")
])
def test_boundaries(units, expected_energy):
    r = calculate_residential_bill(usage=Decimal(units), month=10, year=2569)
    assert r.status == "partial"
    if "?" not in expected_energy:
        assert r.energy == Decimal(expected_energy)

@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), True])
def test_invalid_usage(value):
    with pytest.raises(ValueError):
        calculate_residential_bill(usage=value, month=9, year=2569)

def test_oct_dec_partial_and_unsupported():
    assert calculate_residential_bill(usage="966", month=12, year=2569).status == "partial"
    assert calculate_residential_bill(usage="966", month=9, year=2569, subtype="1.1.1").status == "unavailable"
    assert calculate_residential_bill(usage="966", month=8, year=2569).status == "unavailable"
    assert calculate_residential_bill(usage="966", month=9, year=2026).status == "calculated"
