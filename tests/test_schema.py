import pytest
from pydantic import ValidationError

from invoices.schema import Invoice


def test_valid_payload(gold_dict):
    invoice = Invoice.model_validate(gold_dict)
    assert invoice.total == 1200.0
    assert invoice.items[0].quantity == 2.0


def test_normalizes_dirty_values(gold_dict):
    dirty = gold_dict | {
        "date": "10 травня 2024 року",
        "currency": "грн",
        "total": "1 200,00 грн",
        "vat": "200,00",
        "items": [{"name": "Підтримка", "quantity": "2,0", "unit_price": "500.00"}],
    }
    invoice = Invoice.model_validate(dirty)
    assert invoice.date.isoformat() == "2024-05-10"
    assert invoice.currency == "UAH"
    assert invoice.total == 1200.0 and invoice.vat == 200.0
    assert invoice.items[0].quantity == 2.0


@pytest.mark.parametrize("value", [None, "", "Без ПДВ", "відсутній"])
def test_vat_absent_markers(gold_dict, value):
    assert Invoice.model_validate(gold_dict | {"vat": value}).vat is None


def test_vat_zero_is_not_absent(gold_dict):
    assert Invoice.model_validate(gold_dict | {"vat": 0}).vat == 0.0


def test_vat_key_may_be_missing(gold_dict):
    gold_dict.pop("vat")
    assert Invoice.model_validate(gold_dict).vat is None


@pytest.mark.parametrize(
    "patch",
    [
        {"total": "багато"},
        {"date": "31.02.2024"},
        {"currency": "гроші"},
        {"items": []},
        {"items": [{"name": "x", "quantity": 0, "unit_price": 1}]},
        {"items": [{"name": "x", "quantity": 1}]},
        {"supplier": "   "},
        {"unexpected": 1},
    ],
)
def test_invalid_payloads(gold_dict, patch):
    with pytest.raises(ValidationError):
        Invoice.model_validate(gold_dict | patch)


def test_error_locations_are_reported(gold_dict):
    with pytest.raises(ValidationError) as exc:
        Invoice.model_validate(gold_dict | {"items": [{"name": "x", "quantity": "abc", "unit_price": 1}]})
    locations = {".".join(str(p) for p in err["loc"]) for err in exc.value.errors()}
    assert "items.0.quantity" in locations
