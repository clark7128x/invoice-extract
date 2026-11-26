from invoices.metrics import ALL_FIELDS
from invoices.report import MISSING, render_markdown


def payload(runs):
    return {"dataset": {"path": "data/invoices.jsonl", "rows": 150, "skipped": 0}, "models": runs}


def test_unmeasured_cells():
    markdown = render_markdown(payload([{"key": "small", "model_name": None}]))
    assert markdown.count(MISSING) >= len(ALL_FIELDS)
    assert "Дані синтетичні." in markdown


def test_measured_values_are_formatted():
    run = {
        "key": "small",
        "model_name": "m",
        "validation_rate": 0.9,
        "first_try_valid_rate": 0.75,
        "latency_s": {"p50": 1.0, "p95": 2.0},
        "cost_per_1000": 1.25,
        "fields": {"supplier": {"f1": 0.5}},
        "hallucination": {"absent_fields": 10, "filled_fields": 2, "rate": 0.2},
        "calls": {"calls": 160, "failed": 1, "input_tokens": 1000, "output_tokens": 500,
                  "latency_p50_s": 1.0, "latency_p95_s": 2.0, "cost": 0.5},
    }
    markdown = render_markdown(payload([run]))
    assert "0.900" in markdown and "1.2500" in markdown and "1000" in markdown


def test_skip_reason_is_shown():
    markdown = render_markdown(payload([{"key": "large", "skipped_reason": "не задано LLM_MODEL_LARGE"}]))
    assert "не задано LLM_MODEL_LARGE" in markdown


def test_two_model_columns():
    markdown = render_markdown(payload([{"key": "small"}, {"key": "large"}]))
    assert "| Поле | small | large |" in markdown


def test_empty_model_list():
    assert "## Огляд" in render_markdown(payload([]))
