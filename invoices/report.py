from __future__ import annotations

from .metrics import ALL_FIELDS

MISSING = "не виміряно"


def _fmt(value, spec: str = "{:.3f}") -> str:
    return MISSING if value is None else spec.format(value)


def _ms(value) -> str:
    return MISSING if value is None else f"{value * 1000:.0f}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render_markdown(payload: dict) -> str:
    runs = payload.get("models", [])
    dataset = payload.get("dataset", {})
    lines = [
        "# Результати оцінки",
        "",
        f"Набір: `{dataset.get('path', '—')}`. Документів: {dataset.get('rows', 0)}. "
        f"Пропущено: {dataset.get('skipped', 0)}. Дані синтетичні.",
        "",
        "## Огляд",
        "",
    ]
    lines += _table(
        ["Модель", "Назва", "Валідно", "З першої спроби", "Медіана, мс", "p95, мс", "Вартість / 1000"],
        [
            [
                run.get("key", "—"),
                run.get("model_name") or "—",
                _fmt(run.get("validation_rate")),
                _fmt(run.get("first_try_valid_rate")),
                _ms((run.get("latency_s") or {}).get("p50")),
                _ms((run.get("latency_s") or {}).get("p95")),
                _fmt(run.get("cost_per_1000"), "{:.4f}"),
            ]
            for run in runs
        ],
    )

    lines += ["", "## F1 по полях", ""]
    keys = [run.get("key", "—") for run in runs]
    lines += _table(
        ["Поле", *keys],
        [
            [name] + [_fmt(((run.get("fields") or {}).get(name) or {}).get("f1")) for run in runs]
            for name in ALL_FIELDS
        ],
    )

    lines += ["", "## Вигадані значення у відсутніх полях", ""]
    lines += _table(
        ["Модель", "Відсутніх полів", "Заповнено", "Частка"],
        [
            [
                run.get("key", "—"),
                _fmt((run.get("hallucination") or {}).get("absent_fields"), "{:.0f}"),
                _fmt((run.get("hallucination") or {}).get("filled_fields"), "{:.0f}"),
                _fmt((run.get("hallucination") or {}).get("rate")),
            ]
            for run in runs
        ],
    )

    lines += ["", "## Виклики моделей", ""]
    lines += _table(
        ["Модель", "Викликів", "Помилок", "Вхідні токени", "Вихідні токени", "p50, мс", "p95, мс", "Вартість"],
        [
            [
                run.get("key", "—"),
                _fmt((run.get("calls") or {}).get("calls"), "{:.0f}"),
                _fmt((run.get("calls") or {}).get("failed"), "{:.0f}"),
                _fmt((run.get("calls") or {}).get("input_tokens"), "{:.0f}"),
                _fmt((run.get("calls") or {}).get("output_tokens"), "{:.0f}"),
                _ms((run.get("calls") or {}).get("latency_p50_s")),
                _ms((run.get("calls") or {}).get("latency_p95_s")),
                _fmt((run.get("calls") or {}).get("cost"), "{:.4f}"),
            ]
            for run in runs
        ],
    )

    notes = [f"- {run.get('key')}: {run['skipped_reason']}" for run in runs if run.get("skipped_reason")]
    errors = [f"- {run.get('key')}: {run['error']}" for run in runs if run.get("error")]
    if notes or errors:
        lines += ["", "Пропуски й помилки:", *notes, *errors]
    return "\n".join(lines) + "\n"
