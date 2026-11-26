from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter

from pydantic import ValidationError

from .config import PipelineConfig
from .schema import Invoice, schema_prompt

SYSTEM_PROMPT = """Ти витягуєш структуровані дані з тексту рахунку.
Поверни лише JSON-об'єкт без markdown, без пояснень і без коментарів.
JSON Schema відповіді:
{schema}
Правила:
- date подай у форматі YYYY-MM-DD;
- currency подай кодом ISO 4217 (UAH, USD, EUR, PLN);
- total, vat, quantity, unit_price подай числами без символів валют і пробілів;
- number подай без символу №;
- vat = null, якщо ПДВ у документі не згадано або написано «Без ПДВ»;
- не вигадуй значень, яких немає в тексті;
- items містить усі позиції документа з полями name, quantity, unit_price.
"""

RETRY_PROMPT = """Твоя попередня відповідь не пройшла перевірку.
{error}
Поверни виправлений JSON повністю за тією самою схемою.
Лише JSON, без пояснень і без markdown. Не додавай значень, яких немає в документі.
"""


@dataclass
class ExtractionResult:
    invoice: Invoice | None
    attempts: int
    first_try_valid: bool
    latency_s: float
    errors: list[str] = field(default_factory=list)
    raw_outputs: list[str] = field(default_factory=list)


def build_messages(text: str, max_input_chars: int) -> list[dict[str, str]]:
    if not text or not text.strip():
        raise ValueError("Порожній текст документа")
    system = SYSTEM_PROMPT.format(schema=schema_prompt())
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text[:max_input_chars]},
    ]


def parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("модель не повернула JSON-об'єкт")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"некоректний JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON має бути об'єктом")
    return data


def describe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        rows = []
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"]) or "(корінь)"
            value = json.dumps(error.get("input"), ensure_ascii=False, default=str)[:120]
            rows.append(f"- {location}: {error['msg']} (отримано: {value})")
        return "Помилки валідації схеми:\n" + "\n".join(rows)
    return f"Не вдалося розібрати відповідь: {exc}"


def extract_invoice(
    text: str, client, cfg: PipelineConfig, doc_id: str | None = None
) -> ExtractionResult:
    messages = build_messages(text, cfg.max_input_chars)
    errors: list[str] = []
    raw_outputs: list[str] = []
    started = perf_counter()

    for attempt in range(1, cfg.max_retries + 2):
        result = client.chat(messages, extra={"doc_id": doc_id, "attempt": attempt})
        raw_outputs.append(result.text)
        try:
            invoice = Invoice.model_validate(parse_json(result.text))
        except (ValidationError, ValueError) as exc:
            message = describe_error(exc)
            errors.append(message)
            if attempt <= cfg.max_retries:
                messages = messages + [
                    {"role": "assistant", "content": result.text},
                    {"role": "user", "content": RETRY_PROMPT.format(error=message)},
                ]
                continue
            return ExtractionResult(
                invoice=None,
                attempts=attempt,
                first_try_valid=False,
                latency_s=perf_counter() - started,
                errors=errors,
                raw_outputs=raw_outputs,
            )
        return ExtractionResult(
            invoice=invoice,
            attempts=attempt,
            first_try_valid=attempt == 1,
            latency_s=perf_counter() - started,
            errors=errors,
            raw_outputs=raw_outputs,
        )

    raise AssertionError("цикл завершився без результату")
