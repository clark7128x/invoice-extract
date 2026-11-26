from __future__ import annotations

import random
import re

from .normalize import MONTHS

MONTHS_GENITIVE = {
    1: "січня", 2: "лютого", 3: "березня", 4: "квітня", 5: "травня", 6: "червня",
    7: "липня", 8: "серпня", 9: "вересня", 10: "жовтня", 11: "листопада", 12: "грудня",
}
MONTHS_SHORT = {
    1: "січ", 2: "лют", 3: "бер", 4: "кві", 5: "тра", 6: "чер",
    7: "лип", 8: "сер", 9: "вер", 10: "жов", 11: "лис", 12: "гру",
}
CURRENCY_FORMS = {
    "UAH": ["грн", "₴", "UAH"],
    "USD": ["USD", "$"],
    "EUR": ["EUR", "€"],
    "PLN": ["PLN", "zł"],
}

# Ці слова не спотворюються: від них залежить розбір дати й валюти.
PROTECTED = set(MONTHS) | {"року", "грн", "дол", "євро", "евро", "злотий", "uah", "usd", "eur", "pln"}

NOISE_LINES = [
    "Тел.: +380 44 000 00 00",
    "IBAN UA00 0000 0000 0000 0000 0000 0000",
    "код ЄДРПОУ 00000000",
    "Дякуємо за співпрацю!",
    "Менеджер: Олена",
    "Оплата в межах 5 банківських днів.",
    "-------- Переслане повідомлення --------",
]

_WORD = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+")


def _swap_separators(text: str) -> str:
    return text.translate(str.maketrans({",": ".", ".": ","}))


def format_amount(value: float, style: int) -> str:
    plain = f"{value:.2f}"
    if style == 0:
        return plain
    if style == 1:
        return _swap_separators(f"{value:,.2f}").replace(".", "\u00a0")
    if style == 2:
        return f"{value:,.2f}"
    if style == 3:
        return _swap_separators(f"{value:,.2f}")
    return plain.replace(".", ",")


def format_quantity(value: float, style: int) -> str:
    plain = f"{value:.3f}".rstrip("0").rstrip(".")
    return plain.replace(".", ",") if style in (1, 3, 4) else plain


def format_date(iso: str, style: int) -> str:
    year, month, day = (int(part) for part in iso.split("-"))
    if style == 0:
        return iso
    if style == 1:
        return f"{day:02d}.{month:02d}.{year}"
    if style == 2:
        return f"{day} {MONTHS_GENITIVE[month]} {year} року"
    if style == 3:
        return f"{day:02d}/{month:02d}/{year}"
    return f"{day} {MONTHS_SHORT[month]} {year}"


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 4:
        return word
    position = rng.randrange(len(word) - 1)
    operation = rng.randrange(4)
    if operation == 0:
        return word[:position] + word[position + 1] + word[position] + word[position + 2 :]
    if operation == 1:
        return word[:position] + word[position + 1 :]
    if operation == 2:
        return word[:position] + word[position] + word[position:]
    return word[:position] + rng.choice("аеиіоуя") + word[position + 1 :]


def distort(text: str, rng: random.Random, probability: float) -> str:
    """Опечатки торкаються лише літерних слів, тому числа й дати лишаються точними."""

    def replace(match: re.Match) -> str:
        word = match.group(0)
        if word.casefold() in PROTECTED or len(word) < 4:
            return word
        return _typo(word, rng) if rng.random() < probability else word

    return _WORD.sub(replace, text)


def _vat_line(gold: dict, style: int, label: str) -> str:
    if gold["vat"] is None:
        return "Без ПДВ."
    return f"{label}: {format_amount(gold['vat'], style)}"


def render_invoice(gold: dict, template: int, rng: random.Random, typo_probability: float) -> str:
    style = template
    currency = CURRENCY_FORMS[gold["currency"]][template % len(CURRENCY_FORMS[gold["currency"]])]
    amount = lambda value: format_amount(value, style)  # noqa: E731
    quantity = lambda value: format_quantity(value, style)  # noqa: E731
    date = format_date(gold["date"], style)
    items = gold["items"]

    if template == 0:
        lines = [
            f"РАХУНОК-ФАКТУРА № {gold['number']}",
            f"Дата: {date}",
            f"Постачальник: {gold['supplier']}",
            f"Валюта: {gold['currency']}",
            "",
            "Позиції:",
        ]
        lines += [
            f"{i}. {item['name']} — {quantity(item['quantity'])} x {amount(item['unit_price'])} {currency}"
            for i, item in enumerate(items, start=1)
        ]
        lines += ["", f"Разом: {amount(gold['total'])} {currency}", _vat_line(gold, style, "ПДВ")]

    elif template == 1:
        lines = [
            f"Постачальник: {gold['supplier']}",
            f"Рахунок: {gold['number']}    Дата: {date}",
            "",
            "| Найменування | Кількість | Ціна |",
            "|---|---|---|",
        ]
        lines += [
            f"| {item['name']} | {quantity(item['quantity'])} | {amount(item['unit_price'])} |"
            for item in items
        ]
        lines += [
            "",
            f"Валюта розрахунків: {currency}",
            f"Усього до сплати: {amount(gold['total'])}",
            _vat_line(gold, style, "ПДВ"),
        ]

    elif template == 2:
        lines = [
            f"{gold['supplier']} надсилає рахунок {gold['number']} від {date}.",
            f"Розрахунки у {currency}.",
            "",
        ]
        lines += [
            f"- {item['name']}: {quantity(item['quantity'])} од. за ціною {amount(item['unit_price'])}"
            for item in items
        ]
        lines += ["", f"До сплати {amount(gold['total'])} {currency}.", _vat_line(gold, style, "Сума ПДВ")]

    elif template == 3:
        lines = [
            f"=== {gold['supplier']} ===",
            f"Номер {gold['number']} / {date}",
            f"Валюта {currency}",
        ]
        lines += [
            f"{quantity(item['quantity'])} x {amount(item['unit_price'])}  {item['name']}"
            for item in items
        ]
        lines += [f"ВСЬОГО {amount(gold['total'])} {currency}", _vat_line(gold, style, "ПДВ")]

    else:
        lines = [
            "Від: бухгалтерія",
            f"Тема: рахунок {gold['number']}",
            "",
            gold["supplier"],
            f"Дата виставлення: {date}",
            f"Валюта: {currency}",
            "",
        ]
        lines += [
            f"{item['name']} | {quantity(item['quantity'])} | {amount(item['unit_price'])}"
            for item in items
        ]
        lines += ["", f"Разом до сплати: {amount(gold['total'])} {currency}", _vat_line(gold, style, "ПДВ")]

    for _ in range(rng.randrange(0, 3)):
        noise = rng.choice(NOISE_LINES)
        lines.insert(0 if rng.random() < 0.5 else len(lines), noise)

    return distort("\n".join(lines), rng, typo_probability)


TEMPLATES = (0, 1, 2, 3, 4)
