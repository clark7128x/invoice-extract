import pytest

from invoices.config import PipelineConfig
from invoices.llm import ChatResult
from invoices.schema import Invoice

GOLD = {
    "supplier": "ТОВ «Крига Софт»",
    "number": "INV-2024-0001",
    "date": "2024-05-10",
    "currency": "UAH",
    "total": 1200.0,
    "vat": 200.0,
    "items": [{"name": "Технічна підтримка", "quantity": 2.0, "unit_price": 500.0}],
}


@pytest.fixture
def gold_dict():
    return {**GOLD, "items": [dict(item) for item in GOLD["items"]]}


@pytest.fixture
def gold(gold_dict):
    return Invoice.model_validate(gold_dict)


@pytest.fixture
def pipeline_cfg():
    return PipelineConfig(max_retries=2, max_input_chars=8000)


class ScriptedClient:
    """Повертає заготовлені відповіді й запам'ятовує отримані повідомлення."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def chat(self, messages, extra=None):
        self.calls.append([dict(m) for m in messages])
        if not self.replies:
            raise AssertionError("клієнт викликано більше разів, ніж очікувалось")
        return ChatResult(
            text=self.replies.pop(0),
            model="scripted",
            input_tokens=100,
            output_tokens=50,
            latency_s=0.01,
        )


@pytest.fixture
def scripted():
    return ScriptedClient
