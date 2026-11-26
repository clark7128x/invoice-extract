from invoices.generator import generate
from invoices.schema import Invoice


def test_count_and_ids():
    rows = generate(20, seed=17, vat_absent_probability=0.35, typo_probability=0.06)
    assert len(rows) == 20
    assert [row["id"] for row in rows][:2] == ["inv-0001", "inv-0002"]


def test_same_seed_is_deterministic():
    first = generate(15, 17, 0.35, 0.06)
    second = generate(15, 17, 0.35, 0.06)
    assert first == second


def test_different_seed_changes_text():
    assert generate(5, 17, 0.35, 0.06)[0]["text"] != generate(5, 99, 0.35, 0.06)[0]["text"]


def test_all_five_templates_used():
    rows = generate(15, 17, 0.35, 0.06)
    assert {row["template"] for row in rows} == {1, 2, 3, 4, 5}


def test_gold_validates_and_totals_are_consistent():
    for row in generate(40, 17, 0.35, 0.06):
        invoice = Invoice.model_validate(row["gold"])
        net = round(sum(i.quantity * i.unit_price for i in invoice.items), 2)
        expected = round(net + (invoice.vat or 0.0), 2)
        assert invoice.total == expected


def test_vat_absent_and_present_both_occur():
    rows = generate(60, 17, 0.35, 0.06)
    absent = [row for row in rows if not row["vat_present"]]
    assert 0 < len(absent) < len(rows)
    assert all(row["gold"]["vat"] is None for row in absent)


def test_zero_absent_probability_keeps_vat_everywhere():
    rows = generate(20, 17, 0.0, 0.06)
    assert all(row["vat_present"] for row in rows)


def test_full_absent_probability_removes_vat_everywhere():
    rows = generate(20, 17, 1.0, 0.06)
    assert not any(row["vat_present"] for row in rows)
