from __future__ import annotations

import datetime as dt
import random

from .render import TEMPLATES, render_invoice

SUPPLIERS = [
    "ТОВ «Крига Софт»",
    "ПП «Зоряний Обрій»",
    "ТОВ «Дніпро Логістик»",
    "ФОП Мельник О. І.",
    "ТОВ «Верба Групп»",
    "АТ «Полісся Трейд»",
    "ТОВ «Сонях Медіа»",
    "ПП «Граніт Буд»",
    "ТОВ «Лиман Агро»",
    "ТОВ «Схема Labs»",
]

ITEM_NAMES = [
    "Ліцензія на програмне забезпечення",
    "Технічна підтримка, місяць",
    "Монтаж мережевого обладнання",
    "Кабель UTP cat.6, бухта",
    "Ноутбук службовий",
    "Друк брошур А4",
    "Оренда сервера, місяць",
    "Консультація з аудиту",
    "Кур'єрська доставка",
    "Канцелярський набір",
    "Налаштування резервного копіювання",
    "Заміна фільтра вентиляції",
    "Розробка макета сторінки",
    "Переклад технічної документації",
    "Послуги хостингу",
]

CURRENCIES = ["UAH", "UAH", "UAH", "UAH", "USD", "USD", "EUR", "PLN"]
NUMBER_PREFIXES = ["INV", "РХ", "SF", "A"]
QUANTITIES = [1, 2, 3, 4, 5, 10, 0.5, 1.5, 2.5]
VAT_RATES = [0.20, 0.14, 0.07]


def make_gold(rng: random.Random, index: int) -> dict:
    year = rng.choice([2023, 2024, 2025])
    invoice_date = dt.date(year, 1, 1) + dt.timedelta(days=rng.randrange(0, 360))
    names = rng.sample(ITEM_NAMES, rng.randint(1, 5))
    items = [
        {
            "name": name,
            "quantity": float(rng.choice(QUANTITIES)),
            "unit_price": round(rng.uniform(15, 4800), 2),
        }
        for name in names
    ]
    net = round(sum(item["quantity"] * item["unit_price"] for item in items), 2)
    # ПДВ тут завжди є; відсутність ПДВ вирішує _with_vat_presence за заданою ймовірністю.
    vat = round(net * rng.choice(VAT_RATES), 2)
    return {
        "supplier": rng.choice(SUPPLIERS),
        "number": f"{rng.choice(NUMBER_PREFIXES)}-{year}-{index:04d}",
        "date": invoice_date.isoformat(),
        "currency": rng.choice(CURRENCIES),
        "total": round(net + vat, 2),
        "vat": vat,
        "items": items,
    }


def generate(count: int, seed: int, vat_absent_probability: float, typo_probability: float) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for index in range(1, count + 1):
        gold = _with_vat_presence(make_gold(rng, index), rng, vat_absent_probability)
        template = (index - 1) % len(TEMPLATES)
        text = render_invoice(gold, template, rng, typo_probability)
        rows.append(
            {
                "id": f"inv-{index:04d}",
                "template": template + 1,
                "vat_present": gold["vat"] is not None,
                "text": text,
                "gold": gold,
            }
        )
    return rows


def _with_vat_presence(gold: dict, rng: random.Random, absent_probability: float) -> dict:
    if rng.random() < absent_probability:
        net = round(sum(i["quantity"] * i["unit_price"] for i in gold["items"]), 2)
        gold["vat"] = None
        gold["total"] = net
    return gold
