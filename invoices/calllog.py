from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jsonio import append_jsonl
from .metrics import percentile


class CallLog:
    def __init__(
        self,
        path: str | Path | None = None,
        price_per_1m_input: float | None = None,
        price_per_1m_output: float | None = None,
    ):
        self.path = Path(path) if path is not None else None
        self.price_in = price_per_1m_input
        self.price_out = price_per_1m_output
        self.records: list[dict[str, Any]] = []

    def record(
        self,
        *,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_s: float,
        ok: bool = True,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": "chat",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_s": latency_s,
            "ok": ok,
            "error": error,
        }
        if extra:
            row.update(extra)
        self.records.append(row)
        if self.path is not None:
            append_jsonl(self.path, row)

    def cost(self) -> float | None:
        if self.price_in is None or self.price_out is None or not self.records:
            return None
        total = 0.0
        for row in self.records:
            if row["input_tokens"] is None or row["output_tokens"] is None:
                return None
            total += row["input_tokens"] / 1_000_000 * self.price_in
            total += row["output_tokens"] / 1_000_000 * self.price_out
        return total

    @staticmethod
    def _tokens(field: str, records: list[dict]) -> int | None:
        values = [r[field] for r in records if r[field] is not None]
        return sum(values) if values else None

    def summary(self) -> dict[str, Any]:
        latencies = [r["latency_s"] for r in self.records]
        return {
            "calls": len(self.records),
            "failed": sum(1 for r in self.records if not r["ok"]),
            "input_tokens": self._tokens("input_tokens", self.records),
            "output_tokens": self._tokens("output_tokens", self.records),
            "latency_p50_s": percentile(latencies, 50),
            "latency_p95_s": percentile(latencies, 95),
            "cost": self.cost(),
        }
