from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .normalize import edit_distance, normalize_text
from .schema import Invoice

SCALAR_FIELDS = ("supplier", "number", "date", "currency", "total", "vat")
ITEM_FIELDS = ("name", "quantity", "unit_price")
ALL_FIELDS = SCALAR_FIELDS + ("items",) + tuple(f"items.{name}" for name in ITEM_FIELDS)
TEXT_FIELDS = {"supplier", "items.name", "name"}


@dataclass(frozen=True)
class MatchConfig:
    amount_tolerance: float = 0.01
    name_edit_distance: int = 1


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def merge(self, other: "Counts") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        self.tn += other.tn

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        # Те саме, що гармонійне середнє precision і recall, але без None там,
        # де додатні випадки були, а жоден не збігся: такий F1 дорівнює 0.
        denominator = 2 * self.tp + self.fp + self.fn
        return 2 * self.tp / denominator if denominator else None

    def as_dict(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "precision": self.precision, "recall": self.recall, "f1": self.f1,
        }


def values_equal(field: str, gold, pred, match: MatchConfig) -> bool:
    if field in TEXT_FIELDS:
        left, right = normalize_text(str(gold)), normalize_text(str(pred))
        if left == right:
            return True
        limit = match.name_edit_distance
        return limit > 0 and edit_distance(left, right, limit) <= limit
    if field == "number":
        return normalize_text(str(gold)) == normalize_text(str(pred))
    if field == "date":
        return gold == pred
    if field == "currency":
        return str(gold).upper() == str(pred).upper()
    return abs(float(gold) - float(pred)) <= match.amount_tolerance


def _greedy_match(gold: Sequence, pred: Sequence, equal) -> tuple[int, int, int]:
    used = [False] * len(pred)
    tp = 0
    for gold_value in gold:
        for index, pred_value in enumerate(pred):
            if not used[index] and equal(gold_value, pred_value):
                used[index] = True
                tp += 1
                break
    return tp, len(pred) - tp, len(gold) - tp


def items_equal(gold: dict, pred: dict, match: MatchConfig) -> bool:
    return all(values_equal(name, gold[name], pred[name], match) for name in ITEM_FIELDS)


def score_document(
    gold: Invoice, pred: Invoice | None, match: MatchConfig
) -> tuple[dict[str, Counts], list[str], list[str]]:
    fields = {name: Counts() for name in ALL_FIELDS}
    absent: list[str] = []
    hallucinated: list[str] = []
    gold_data = gold.model_dump()
    pred_data = pred.model_dump() if pred is not None else None

    for name in SCALAR_FIELDS:
        gold_value = gold_data[name]
        pred_value = pred_data[name] if pred_data is not None else None
        if gold_value is None:
            absent.append(name)
            if pred_value is None:
                fields[name].tn += 1
            else:
                fields[name].fp += 1
                hallucinated.append(name)
            continue
        if pred_value is None:
            fields[name].fn += 1
        elif values_equal(name, gold_value, pred_value, match):
            fields[name].tp += 1
        else:
            fields[name].fp += 1
            fields[name].fn += 1

    gold_items = gold_data["items"]
    pred_items = pred_data["items"] if pred_data is not None else []
    tp, fp, fn = _greedy_match(gold_items, pred_items, lambda g, p: items_equal(g, p, match))
    fields["items"].tp, fields["items"].fp, fields["items"].fn = tp, fp, fn

    for name in ITEM_FIELDS:
        tp, fp, fn = _greedy_match(
            [item[name] for item in gold_items],
            [item[name] for item in pred_items],
            lambda g, p, field=name: values_equal(field, g, p, match),
        )
        fields[f"items.{name}"].tp, fields[f"items.{name}"].fp, fields[f"items.{name}"].fn = tp, fp, fn

    return fields, absent, hallucinated


def aggregate(scores: list[tuple[dict[str, Counts], list[str], list[str]]]) -> dict:
    totals = {name: Counts() for name in ALL_FIELDS}
    absent_counts = {name: 0 for name in SCALAR_FIELDS}
    hallucination_counts = {name: 0 for name in SCALAR_FIELDS}
    for fields, absent, hallucinated in scores:
        for name, counts in fields.items():
            totals[name].merge(counts)
        for name in absent:
            absent_counts[name] += 1
        for name in hallucinated:
            hallucination_counts[name] += 1

    absent_total = sum(absent_counts.values())
    hallucinated_total = sum(hallucination_counts.values())
    return {
        "fields": {name: counts.as_dict() for name, counts in totals.items()},
        "hallucination": {
            "absent_fields": absent_total,
            "filled_fields": hallucinated_total,
            "rate": hallucinated_total / absent_total if absent_total else None,
            "by_field": {
                name: {
                    "absent": absent_counts[name],
                    "filled": hallucination_counts[name],
                    "rate": (
                        hallucination_counts[name] / absent_counts[name]
                        if absent_counts[name]
                        else None
                    ),
                }
                for name in SCALAR_FIELDS
            },
        },
    }


def percentile(values: Sequence[float], p: float) -> float | None:
    if not 0 <= p <= 100:
        raise ValueError("p має бути в [0, 100]")
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return float(ordered[index])


def latency_stats(values: Sequence[float]) -> dict:
    if not values:
        return {"mean": None, "p50": None, "p95": None, "max": None}
    return {
        "mean": sum(values) / len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values),
    }


def cost_per_1000(cost_total: float | None, documents: int) -> float | None:
    if cost_total is None or documents <= 0:
        return None
    return cost_total / documents * 1000
