from __future__ import annotations

import datetime as dt
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .normalize import is_absent, normalize_amount, normalize_currency, normalize_date

Amount = Annotated[float, Field(ge=0)]
Quantity = Annotated[float, Field(gt=0)]


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    quantity: Quantity
    unit_price: Amount

    @field_validator("quantity", "unit_price", mode="before")
    @classmethod
    def _numbers(cls, value):
        return normalize_amount(value)


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    supplier: str = Field(min_length=1)
    number: str = Field(min_length=1)
    date: dt.date
    currency: str
    total: Amount
    vat: Amount | None = None
    items: list[LineItem] = Field(min_length=1)

    @field_validator("date", mode="before")
    @classmethod
    def _date(cls, value):
        return normalize_date(value)

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, value):
        return normalize_currency(value)

    @field_validator("total", mode="before")
    @classmethod
    def _total(cls, value):
        return normalize_amount(value)

    @field_validator("vat", mode="before")
    @classmethod
    def _vat(cls, value):
        return None if is_absent(value) else normalize_amount(value)


def schema_prompt() -> str:
    return json.dumps(Invoice.model_json_schema(), ensure_ascii=False, indent=2)
