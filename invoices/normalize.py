from __future__ import annotations

import datetime as dt
import math
import re

MONTHS = {
    "січня": 1, "січ": 1, "січень": 1,
    "лютого": 2, "лют": 2, "лютий": 2,
    "березня": 3, "бер": 3, "березень": 3,
    "квітня": 4, "кві": 4, "квітень": 4,
    "травня": 5, "тра": 5, "травень": 5,
    "червня": 6, "чер": 6, "червень": 6,
    "липня": 7, "лип": 7, "липень": 7,
    "серпня": 8, "сер": 8, "серпень": 8,
    "вересня": 9, "вер": 9, "вересень": 9,
    "жовтня": 10, "жов": 10, "жовтень": 10,
    "листопада": 11, "лис": 11, "листопад": 11,
    "грудня": 12, "гру": 12, "грудень": 12,
}

CURRENCY_CODES = {
    "ГРН": "UAH", "₴": "UAH", "UAH": "UAH", "HRYVNIA": "UAH",
    "$": "USD", "USD": "USD", "ДОЛ": "USD", "ДОЛАР": "USD",
    "€": "EUR", "EUR": "EUR", "ЄВРО": "EUR", "ЕВРО": "EUR",
    "ZŁ": "PLN", "PLN": "PLN", "ЗЛ": "PLN", "ЗЛОТИЙ": "PLN",
}

ABSENT_MARKERS = {"", "-", "—", "–", "n/a", "н/д", "null", "none", "відсутній", "відсутнє",
                  "немає", "без пдв", "не нараховується"}

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMERIC_DATE = re.compile(r"(\d{1,4})[./\-](\d{1,2})[./\-](\d{1,4})")
_TEXT_DATE = re.compile(r"(\d{1,2}) ([а-яіїєґ']+)\.? (\d{4})")
_CURRENCY_IN_AMOUNT = re.compile(r"(₴|\$|€|zł|грн\.?|uah|usd|eur|pln|дол\.?|євро|евро)", re.I)
_NUMBER = re.compile(r"-?\d+(\.\d+)?")
_QUOTES = "«»\"'“”„‟"
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "`": "'"})


def is_absent(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold().strip(_QUOTES) in ABSENT_MARKERS
    return False


def normalize_text(value: str) -> str:
    text = value.translate(_APOSTROPHES).casefold()
    text = "".join(" " if ch in _QUOTES else ch for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_date(value: object) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"дата має бути рядком, отримано {type(value).__name__}")

    text = re.sub(r"\s+", " ", value).strip()
    text = re.sub(r"\s*(?:року|р\.?)$", "", text, flags=re.I).strip()
    text = text.rstrip(".").strip()
    if not text:
        raise ValueError("дата порожня")

    if _ISO_DATE.fullmatch(text):
        return dt.date.fromisoformat(text)

    numeric = _NUMERIC_DATE.fullmatch(text)
    if numeric:
        first, middle, last = numeric.groups()
        if len(first) == 4:
            year, month, day = int(first), int(middle), int(last)
        elif len(last) == 4:
            day, month, year = int(first), int(middle), int(last)
        else:
            raise ValueError(f"неоднозначний рік у даті: {value!r}")
        return dt.date(year, month, day)

    textual = _TEXT_DATE.fullmatch(text.casefold())
    if textual:
        day, month_word, year = textual.groups()
        month = MONTHS.get(month_word)
        if month is None:
            raise ValueError(f"невідома назва місяця: {month_word!r}")
        return dt.date(int(year), month, int(day))

    raise ValueError(f"нерозпізнаний формат дати: {value!r}")


def normalize_currency(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"валюта має бути рядком, отримано {type(value).__name__}")
    text = re.sub(r"\s+", "", value).upper().rstrip(".")
    if not text:
        raise ValueError("валюта порожня")
    code = CURRENCY_CODES.get(text, text)
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(f"нерозпізнана валюта: {value!r}")
    return code


def normalize_amount(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("булеве значення не є сумою")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("сума має бути скінченним числом")
        return number
    if not isinstance(value, str):
        raise ValueError(f"сума має бути числом або рядком, отримано {type(value).__name__}")

    text = _CURRENCY_IN_AMOUNT.sub("", value)
    text = re.sub(r"\s+", "", text).strip(_QUOTES)
    if not text:
        raise ValueError("сума порожня")

    comma, dot = text.rfind(","), text.rfind(".")
    if comma >= 0 and dot >= 0:
        # Розділювач, що стоїть правіше, вважаємо десятковим.
        decimal, thousands = (",", ".") if comma > dot else (".", ",")
        text = text.replace(thousands, "").replace(decimal, ".")
    elif comma >= 0:
        text = text.replace(",", "") if text.count(",") > 1 else text.replace(",", ".")
    elif dot >= 0 and text.count(".") > 1:
        text = text.replace(".", "")

    if not _NUMBER.fullmatch(text):
        raise ValueError(f"нерозпізнаний формат суми: {value!r}")
    return float(text)


def edit_distance(a: str, b: str, limit: int | None = None) -> int:
    if a == b:
        return 0
    if limit is not None and abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b))
            )
        if limit is not None and min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]
