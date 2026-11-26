import random
import re

import pytest

from invoices.generator import make_gold
from invoices.normalize import normalize_amount, normalize_date
from invoices.render import (
    TEMPLATES,
    distort,
    format_amount,
    format_date,
    render_invoice,
)


@pytest.mark.parametrize("template", TEMPLATES)
def test_rendered_values_parse_back_to_gold(template):
    gold = make_gold(random.Random(7), 1)
    gold["vat"] = 240.0
    gold["total"] = 1240.0
    text = render_invoice(gold, template, random.Random(7), typo_probability=0.0)
    assert gold["number"] in text
    assert normalize_date(format_date(gold["date"], template)) == normalize_date(gold["date"])
    assert normalize_amount(format_amount(gold["total"], template)) == pytest.approx(gold["total"])
    assert format_amount(gold["total"], template) in text


@pytest.mark.parametrize("template", TEMPLATES)
def test_absent_vat_has_no_amount_line(template):
    gold = make_gold(random.Random(11), 2)
    gold["vat"] = None
    text = render_invoice(gold, template, random.Random(11), typo_probability=0.0)
    assert "Без ПДВ" in text
    assert not re.search(r"ПДВ[^:\n]*:\s*[\d]", text)


def test_typos_never_change_digits():
    text = "Разом: 1 234,56 грн\nДата: 10.05.2024\nТехнічна підтримка"
    distorted = distort(text, random.Random(3), probability=1.0)
    assert re.findall(r"[\d.,]+", distorted) == re.findall(r"[\d.,]+", text)


def test_typos_skip_protected_month_and_currency():
    text = "10 травня 2024 року, разом 100 грн"
    distorted = distort(text, random.Random(5), probability=1.0)
    assert "травня" in distorted and "року" in distorted and "грн" in distorted


def test_zero_probability_keeps_text():
    text = "Технічна підтримка та монтаж обладнання"
    assert distort(text, random.Random(1), 0.0) == text


def test_amount_styles_differ():
    values = {format_amount(1234.56, style) for style in TEMPLATES}
    assert len(values) == 5
