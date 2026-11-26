#!/usr/bin/env python3
"""Оцінка двох моделей на синтетичному наборі рахунків."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from invoices.calllog import CallLog
from invoices.config import ConfigError, load_config
from invoices.jsonio import read_jsonl, write_jsonl
from invoices.llm import LLMClient, LLMError
from invoices.metrics import MatchConfig, aggregate, cost_per_1000, latency_stats, score_document
from invoices.pipeline import extract_invoice
from invoices.report import render_markdown
from invoices.schema import Invoice


def load_rows(path: Path) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], [f"немає файлу {path}"]
    rows: list[dict] = []
    problems: list[str] = []
    for number, raw in enumerate(read_jsonl(path), start=1):
        doc_id, text, gold = raw.get("id"), raw.get("text"), raw.get("gold")
        if not isinstance(doc_id, str) or not doc_id:
            problems.append(f"рядок {number}: немає id")
            continue
        if not isinstance(text, str) or not text.strip():
            problems.append(f"рядок {number}: порожній текст")
            continue
        try:
            parsed = Invoice.model_validate(gold)
        except ValidationError as exc:
            problems.append(f"рядок {number}: gold не проходить схему ({exc.error_count()} помилок)")
            continue
        rows.append({"id": doc_id, "text": text, "gold": parsed, "template": raw.get("template")})
    return rows, problems


def evaluate_model(cfg, key: str, rows: list[dict], match: MatchConfig) -> tuple[dict, list[dict]]:
    model = cfg.model(key)
    run = {
        "key": key,
        "model_name": model.model,
        "documents": len(rows),
        "skipped_reason": None,
        "error": None,
    }
    if not cfg.llm.base_url or not model.configured:
        run["skipped_reason"] = "не задано LLM_API_BASE або назву моделі"
        return run, []

    call_log = CallLog(cfg.eval.call_log, model.price_per_1m_input, model.price_per_1m_output)
    client = LLMClient(cfg.llm, model, call_log)
    scores: list = []
    details: list[dict] = []
    latencies: list[float] = []
    attempts: dict[str, int] = {}
    validated = 0
    first_try = 0
    failed_calls = 0

    for row in rows:
        try:
            result = extract_invoice(row["text"], client, cfg.pipeline, doc_id=row["id"])
        except (LLMError, ValueError) as exc:
            failed_calls += 1
            details.append({"model": key, "id": row["id"], "error": str(exc)})
            scores.append(score_document(row["gold"], None, match))
            continue

        latencies.append(result.latency_s)
        attempts[str(result.attempts)] = attempts.get(str(result.attempts), 0) + 1
        validated += result.invoice is not None
        first_try += result.first_try_valid
        scores.append(score_document(row["gold"], result.invoice, match))
        details.append(
            {
                "model": key,
                "id": row["id"],
                "template": row["template"],
                "attempts": result.attempts,
                "first_try_valid": result.first_try_valid,
                "latency_s": result.latency_s,
                "prediction": result.invoice.model_dump(mode="json") if result.invoice else None,
                "gold": row["gold"].model_dump(mode="json"),
                "errors": result.errors,
            }
        )

    summary = aggregate(scores)
    calls = call_log.summary()
    run.update(
        {
            "validated": validated,
            "failed_documents": failed_calls,
            "validation_rate": validated / len(rows) if rows else None,
            "first_try_valid_rate": first_try / len(rows) if rows else None,
            "attempts_histogram": attempts,
            "fields": summary["fields"],
            "hallucination": summary["hallucination"],
            "latency_s": latency_stats(latencies),
            "calls": calls,
            "cost_total": calls["cost"],
            "cost_per_1000": cost_per_1000(calls["cost"], len(rows)),
        }
    )
    return run, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        keys = args.models or list(cfg.eval.models)
        for key in keys:
            cfg.model(key)
        rows, problems = load_rows(cfg.eval.dataset)
    except (ConfigError, ValueError) as exc:
        print(f"Вхідні дані: {exc}", file=sys.stderr)
        return 2

    for problem in problems:
        print(f"Пропущено: {problem}", file=sys.stderr)
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        print(
            "Набір порожній. Запусти generate_data.py і повтори eval.py. "
            "Метрики не рахуються на вигаданих даних.",
            file=sys.stderr,
        )
        return 2

    match = MatchConfig(cfg.eval.amount_tolerance, cfg.eval.name_edit_distance)
    runs: list[dict] = []
    details: list[dict] = []
    for key in keys:
        run, model_details = evaluate_model(cfg, key, rows, match)
        runs.append(run)
        details.extend(model_details)

    payload = {
        "run_id": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "synthetic": True,
        "config": {
            "pipeline": {"max_retries": cfg.pipeline.max_retries},
            "match": {"amount_tolerance": match.amount_tolerance,
                      "name_edit_distance": match.name_edit_distance},
            "data": {"seed": cfg.data.seed, "count": cfg.data.count},
        },
        "dataset": {
            "path": str(cfg.eval.dataset),
            "rows": len(rows),
            "skipped": len(problems),
            "problems": problems,
        },
        "models": runs,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_dir = cfg.eval.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"eval_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(results_dir / f"details_{stamp}.jsonl", details)
    markdown = render_markdown(payload)
    (results_dir / "metrics.md").write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
