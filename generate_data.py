#!/usr/bin/env python3
"""Створює синтетичні рахунки: спершу правильний JSON, потім текст із нього."""
from __future__ import annotations

import argparse
import sys

from invoices.config import ConfigError, load_config
from invoices.generator import generate
from invoices.jsonio import write_jsonl
from invoices.schema import Invoice


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--out")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"Конфіг: {exc}", file=sys.stderr)
        return 2

    count = args.count if args.count is not None else cfg.data.count
    seed = args.seed if args.seed is not None else cfg.data.seed
    out = args.out or cfg.data.out
    if count <= 0:
        print("count має бути > 0", file=sys.stderr)
        return 2

    rows = generate(count, seed, cfg.data.vat_absent_probability, cfg.data.typo_probability)
    for row in rows:
        Invoice.model_validate(row["gold"])
    write_jsonl(out, rows)

    absent = sum(1 for row in rows if not row["vat_present"])
    templates = sorted({row["template"] for row in rows})
    print(f"Записано {len(rows)} синтетичних рахунків у {out}")
    print(f"Seed: {seed}. Шаблони: {templates}. Без ПДВ у тексті: {absent} з {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
