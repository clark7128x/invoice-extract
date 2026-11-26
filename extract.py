#!/usr/bin/env python3
"""Витягує JSON з одного рахунку: файл або stdin."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from invoices.calllog import CallLog
from invoices.config import ConfigError, load_config
from invoices.llm import LLMClient, LLMError
from invoices.pipeline import extract_invoice


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="файл із текстом рахунку; без нього читає stdin")
    parser.add_argument("--config")
    parser.add_argument("--model", default="small")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        model = cfg.model(args.model)
    except ConfigError as exc:
        print(f"Конфіг: {exc}", file=sys.stderr)
        return 2

    text = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
    call_log = CallLog(
        cfg.eval.results_dir / "extract_calls.jsonl",
        model.price_per_1m_input,
        model.price_per_1m_output,
    )
    client = LLMClient(cfg.llm, model, call_log)

    try:
        result = extract_invoice(text, client, cfg.pipeline)
    except (LLMError, ValueError) as exc:
        print(f"Помилка: {exc}", file=sys.stderr)
        return 1

    if result.invoice is None:
        print("Валідація не пройдена після всіх спроб.", file=sys.stderr)
        for error in result.errors:
            print(error, file=sys.stderr)
        return 1

    print(json.dumps(result.invoice.model_dump(mode="json"), ensure_ascii=False, indent=2))
    summary = call_log.summary()
    print(
        f"\nСпроб: {result.attempts}. Викликів: {summary['calls']}. "
        f"Затримка: {result.latency_s:.2f} с. Вартість: {summary['cost']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
