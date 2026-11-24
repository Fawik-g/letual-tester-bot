"""Наполнить базу демо-данными: 3 магазина с тестерами.

Запуск: python seed_demo.py
Если базы ещё нет — она создастся автоматически.
"""
import asyncio

import db
import services.qr as qr

STORES = [
    ("Лэтуаль — ТЦ «Атриум»", "Москва, Земляной Вал, 33"),
    ("Лэтуаль — МЕGA Химки", "Химки, Ленинградское шоссе, 5"),
    ("Лэтуаль — ТЦ «Европейский»", "Москва, Комсомольская площадь, 2"),
]

# (бренд, продукт, место) — одинаковый набор для каждого магазина
TESTERS = [
    ("Lancôme", "La Vie Est Belle, 50 мл", "Люкс-зона, витрина 2"),
    ("Yves Saint Laurent", "Libre, 50 мл", "Люкс-зона, витрина 2"),
    ("Dior", "J'adore, 50 мл", "Полка 3, парфюмерия"),
    ("Chanel", "Coco Mademoiselle, 50 мл", "Полка 3, парфюмерия"),
    ("Guerlain", "Aqua Allegoria Nerolia, 75 мл", "Полка 4, парфюмерия"),
    ("Givenchy", "L'Interdit, 50 мл", "Полка 4, парфюмерия"),
    ("Narciso Rodriguez", "For Her, 50 мл", "Полка 5, парфюмерия"),
    ("Giorgio Armani", "Si, 50 мл", "Полка 5, парфюмерия"),
    ("Mugler", "Angel, 50 мл", "Прикассовая зона"),
    ("Cartier", "Must de Cartier, 50 мл", "Прикассовая зона"),
]


async def gen_unique_code() -> str:
    while True:
        code = qr.gen_tester_code()
        if not await db.fetchone("SELECT id FROM testers WHERE code = ?", (code,)):
            return code


async def main() -> None:
    await db.init()
    try:
        await seed()
    finally:
        await db.close()


async def seed() -> None:
    print("Демо-данные:")
    for name, address in STORES:
        existing = await db.fetchone("SELECT id FROM stores WHERE name = ?", (name,))
        if existing:
            print(f"• {name} — уже существует, пропускаю")
            continue
        store_id = await db.execute(
            "INSERT INTO stores (name, address) VALUES (?, ?)", (name, address)
        )
        for brand, product, location in TESTERS:
            code = await gen_unique_code()
            await db.execute(
                "INSERT INTO testers (store_id, code, brand, product, location) VALUES (?, ?, ?, ?, ?)",
                (store_id, code, brand, product, location),
            )
        count = await db.fetchone(
            "SELECT COUNT(*) AS n FROM testers WHERE store_id = ?", (store_id,)
        )
        print(f"✅ {name} (id={store_id}) — тестеров: {count['n']}")

    total = await db.fetchone("SELECT COUNT(*) AS n FROM testers")
    print(f"\nВсего тестеров в базе: {total['n']}")
    print("QR-коды для печати сгенерируйте в боте: /admin → Магазины → магазин → «QR-коды магазина».")


if __name__ == "__main__":
    asyncio.run(main())
