import json

import pytest

from invoices.config import PipelineConfig
from invoices.pipeline import build_messages, extract_invoice, parse_json


def test_first_attempt_success(scripted, gold_dict, pipeline_cfg):
    client = scripted([json.dumps(gold_dict)])
    result = extract_invoice("текст рахунку", client, pipeline_cfg, doc_id="inv-0001")
    assert result.invoice is not None
    assert result.attempts == 1 and result.first_try_valid is True
    assert result.errors == [] and len(client.calls) == 1


def test_success_on_second_attempt(scripted, gold_dict, pipeline_cfg):
    broken = gold_dict | {"total": "багато"}
    client = scripted([json.dumps(broken), json.dumps(gold_dict)])
    result = extract_invoice("текст", client, pipeline_cfg)
    assert result.invoice is not None
    assert result.attempts == 2 and result.first_try_valid is False
    assert "Помилки валідації схеми" in result.errors[0]
    assert "total" in result.errors[0]
    assert client.calls[1][-1]["role"] == "user"
    assert "Помилки валідації" in client.calls[1][-1]["content"]
    assert len(client.calls[1]) == len(client.calls[0]) + 2


def test_two_failed_retries_give_up(scripted, gold_dict, pipeline_cfg):
    broken = json.dumps(gold_dict | {"currency": "гроші"})
    client = scripted([broken, broken, broken])
    result = extract_invoice("текст", client, pipeline_cfg)
    assert result.invoice is None
    assert result.attempts == 3 and result.first_try_valid is False
    assert len(result.errors) == 3 and len(client.calls) == 3
    assert len(client.calls[2]) == len(client.calls[0]) + 4


def test_non_json_replies_also_retry(scripted, pipeline_cfg):
    client = scripted(["не json", "ще не json", "і знову не json"])
    result = extract_invoice("текст", client, pipeline_cfg)
    assert result.invoice is None and result.attempts == 3
    assert all("Не вдалося розібрати відповідь" in error for error in result.errors)


def test_zero_retries_means_single_attempt(scripted, gold_dict):
    client = scripted(["не json"])
    result = extract_invoice("текст", client, PipelineConfig(max_retries=0))
    assert result.invoice is None and result.attempts == 1 and len(client.calls) == 1


def test_empty_text_rejected_before_call(scripted, pipeline_cfg):
    client = scripted([])
    with pytest.raises(ValueError):
        extract_invoice("   ", client, pipeline_cfg)
    assert client.calls == []


@pytest.mark.parametrize(
    "raw",
    ['{"a": 1}', '```json\n{"a": 1}\n```', 'Ось відповідь:\n{"a": 1}\nДякую.'],
)
def test_parse_json_accepts_fences_and_prose(raw):
    assert parse_json(raw) == {"a": 1}


@pytest.mark.parametrize("raw", ["", "немає дужок", "[1, 2]", "{не json}"])
def test_parse_json_rejects_bad_input(raw):
    with pytest.raises(ValueError):
        parse_json(raw)


def test_prompt_contains_schema_and_document():
    messages = build_messages("ТЕКСТ-РАХУНОК", 8000)
    assert "unit_price" in messages[0]["content"]
    assert "vat = null" in messages[0]["content"]
    assert messages[1]["content"] == "ТЕКСТ-РАХУНОК"


def test_input_is_truncated():
    messages = build_messages("а" * 500, 100)
    assert len(messages[1]["content"]) == 100
