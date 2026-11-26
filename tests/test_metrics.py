import pytest

from invoices.metrics import (
    Counts,
    MatchConfig,
    aggregate,
    cost_per_1000,
    latency_stats,
    percentile,
    score_document,
)
from invoices.schema import Invoice

MATCH = MatchConfig(amount_tolerance=0.01, name_edit_distance=1)


def counts(gold: Invoice, pred: Invoice | None, field: str) -> Counts:
    fields, _, _ = score_document(gold, pred, MATCH)
    return fields[field]


def test_exact_match_counts_tp(gold):
    assert counts(gold, gold, "supplier").tp == 1
    assert counts(gold, gold, "items").tp == 1


def test_wrong_value_counts_fp_and_fn(gold, gold_dict):
    pred = Invoice.model_validate(gold_dict | {"total": 999.0})
    score = counts(gold, pred, "total")
    assert (score.tp, score.fp, score.fn) == (0, 1, 1)


def test_missing_prediction_counts_fn(gold, gold_dict):
    pred = Invoice.model_validate(gold_dict | {"vat": None})
    score = counts(gold, pred, "vat")
    assert (score.tp, score.fp, score.fn, score.tn) == (0, 0, 1, 0)


def test_absent_in_both_counts_tn(gold, gold_dict):
    gold_absent = Invoice.model_validate(gold_dict | {"vat": None})
    pred = Invoice.model_validate(gold_dict | {"vat": None})
    score = counts(gold_absent, pred, "vat")
    assert (score.tp, score.fp, score.fn, score.tn) == (0, 0, 0, 1)
    assert score.f1 is None


def test_absent_in_gold_only_counts_fp_and_hallucination(gold_dict):
    gold_absent = Invoice.model_validate(gold_dict | {"vat": None})
    pred = Invoice.model_validate(gold_dict | {"vat": 200.0})
    fields, absent, hallucinated = score_document(gold_absent, pred, MATCH)
    assert (fields["vat"].fp, fields["vat"].tn) == (1, 0)
    assert absent == ["vat"] and hallucinated == ["vat"]


def test_failed_extraction_counts_all_gold_as_fn(gold):
    fields, absent, hallucinated = score_document(gold, None, MATCH)
    assert fields["supplier"].fn == 1
    assert fields["items"].fn == 1
    assert fields["items.name"].fn == 1
    assert absent == [] and hallucinated == []


def test_name_tolerates_one_typo(gold, gold_dict):
    items = [gold_dict["items"][0] | {"name": "Технічна підтримкa"}]
    pred = Invoice.model_validate(gold_dict | {"items": items})
    assert counts(gold, pred, "items").tp == 1


def test_name_rejects_two_edits(gold, gold_dict):
    items = [gold_dict["items"][0] | {"name": "Технічна підтрим"}]
    pred = Invoice.model_validate(gold_dict | {"items": items})
    assert counts(gold, pred, "items").tp == 0


def test_number_is_strict(gold, gold_dict):
    pred = Invoice.model_validate(gold_dict | {"number": "INV-2024-0002"})
    assert counts(gold, pred, "number").tp == 0


def test_amount_tolerance_boundary(gold, gold_dict):
    inside = Invoice.model_validate(gold_dict | {"total": gold.total + 0.009})
    outside = Invoice.model_validate(gold_dict | {"total": gold.total + 0.02})
    assert counts(gold, inside, "total").tp == 1
    assert counts(gold, outside, "total").tp == 0


def test_extra_and_missing_items(gold, gold_dict):
    extra_item = {"name": "Зайва позиція", "quantity": 1.0, "unit_price": 10.0}
    pred = Invoice.model_validate(gold_dict | {"items": gold_dict["items"] + [extra_item]})
    score = counts(gold, pred, "items")
    assert (score.tp, score.fp, score.fn) == (1, 1, 0)


def test_item_order_does_not_matter(gold, gold_dict):
    second = {"name": "Монтаж", "quantity": 1.0, "unit_price": 30.0}
    gold_two = Invoice.model_validate(gold_dict | {"items": gold_dict["items"] + [second]})
    pred = Invoice.model_validate(gold_dict | {"items": [second] + gold_dict["items"]})
    assert counts(gold_two, pred, "items").tp == 2


def test_aggregate_f1_and_hallucination_rate(gold, gold_dict):
    gold_absent = Invoice.model_validate(gold_dict | {"vat": None})
    scores = [
        score_document(gold, gold, MATCH),
        score_document(gold_absent, Invoice.model_validate(gold_dict | {"vat": 5.0}), MATCH),
        score_document(gold_absent, gold_absent, MATCH),
    ]
    summary = aggregate(scores)
    assert summary["fields"]["supplier"]["f1"] == pytest.approx(1.0)
    assert summary["hallucination"]["absent_fields"] == 2
    assert summary["hallucination"]["filled_fields"] == 1
    assert summary["hallucination"]["rate"] == pytest.approx(0.5)


def test_aggregate_empty_returns_none():
    summary = aggregate([])
    assert summary["fields"]["supplier"]["f1"] is None
    assert summary["hallucination"]["rate"] is None


@pytest.mark.parametrize(
    "tp,fp,fn,expected",
    [(2, 0, 0, 1.0), (1, 1, 1, 0.5), (0, 1, 1, 0.0), (0, 0, 0, None)],
)
def test_counts_f1(tp, fp, fn, expected):
    value = Counts(tp=tp, fp=fp, fn=fn).f1
    assert value == expected if expected is None else value == pytest.approx(expected)


def test_percentile_and_latency():
    assert percentile([1.0], 95) == 1.0
    assert percentile([], 50) is None
    assert latency_stats([])["p95"] is None
    assert latency_stats([1.0, 3.0])["p50"] == 1.0
    with pytest.raises(ValueError):
        percentile([1.0], 101)


def test_cost_per_1000():
    assert cost_per_1000(2.0, 100) == pytest.approx(20.0)
    assert cost_per_1000(None, 100) is None
    assert cost_per_1000(2.0, 0) is None


def test_f1_is_zero_when_every_prediction_missed(gold):
    fields, _, _ = score_document(gold, None, MATCH)
    assert fields["supplier"].f1 == 0.0
    assert fields["items"].f1 == 0.0
