"""Автономный smoke-тест логики без Telegram: БД, жалобы, обходы, QR.

Запуск: python smoke_test.py  (создаёт и удаляет временную базу smoke_test.db)
"""
import asyncio
import io
import os
import zipfile
from datetime import date

# Временная база и тестовый админ — до импорта модулей, читающих config
ADMIN_TG, STAFF_TG, CUSTOMER_TG = 111, 222, 333
os.environ["DB_PATH"] = "smoke_test.db"
os.environ["ADMIN_IDS"] = str(ADMIN_TG)

import db  # noqa: E402
import notifier  # noqa: E402
import services.checkups as checkups  # noqa: E402
import services.complaints as complaints  # noqa: E402
import services.qr as qr  # noqa: E402
import services.users as users  # noqa: E402


def check(name: str, cond: bool) -> None:
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}")
    if not cond:
        raise SystemExit(f"Тест провален: {name}")


async def main() -> None:
    if os.path.exists("smoke_test.db"):
        os.remove("smoke_test.db")

    await db.init()
    try:
        await run_checks()
    finally:
        await db.close()


async def run_checks() -> None:
    # --- магазин и тестеры (сначала — на них ссылаются сотрудники и жалобы)
    store_id = await db.execute(
        "INSERT INTO stores (name, address) VALUES ('Тест-магазин', 'ул. Тестовая 1')"
    )
    code = qr.gen_tester_code()
    tester_id = await db.execute(
        "INSERT INTO testers (store_id, code, brand, product, location) VALUES (?, ?, ?, ?, ?)",
        (store_id, code, "Dior", "J'adore 50мл", "Полка 1"),
    )
    found = await complaints.find_tester_by_code(code.lower())
    check("тестер находится по коду (без регистра)", found and found["id"] == tester_id)

    # --- пользователи и роли
    await users.upsert(ADMIN_TG, "Админ Тестов", "admin_bot")
    await users.upsert(STAFF_TG, "Сотрудник Тестов", "staff_bot")
    await users.upsert(CUSTOMER_TG, "Покупатель", None)
    await users.set_staff(STAFF_TG, store_id)
    admin = await users.get(ADMIN_TG)
    staff = await users.get(STAFF_TG)
    check("админ получил роль admin", admin["role"] == "admin")
    check("сотрудник привязан к магазину",
          staff["role"] == "employee" and staff["store_id"] == store_id)

    # --- жалоба: создание → взятие → решение
    cid = await complaints.create(tester_id, CUSTOMER_TG, "empty", "совсем пустой", "photo123")
    c = await complaints.get_with_context(cid)
    check("жалоба создана со статусом new", c["status"] == "new" and c["store_name"] == "Тест-магазин")
    await complaints.take(cid, STAFF_TG)
    c = await complaints.get_with_context(cid)
    check("жалоба взята в работу", c["status"] == "in_progress" and c["taken_by_name"])
    await complaints.resolve(cid, STAFF_TG, "заменил тестер")
    c = await complaints.get_with_context(cid)
    check("жалоба решена с резолюцией", c["status"] == "resolved" and c["resolution"] == "заменил тестер")
    check("карточка жалобы содержит данные", "Жалоба №" in complaints.card(c) and "Dior" in complaints.card(c))
    check("открытых жалоб нет", await complaints.open_for_store(store_id) == [])

    # --- регресс: карточка открытой жалобы не падает без store_name в словаре
    cid2 = await complaints.create(tester_id, CUSTOMER_TG, "dirty", "", None)
    opened = await complaints.open_for_store(store_id)
    check("список открытых жалоб содержит store_name",
          len(opened) == 1 and opened[0]["store_name"] == "Тест-магазин")
    bare = dict(opened[0])
    bare.pop("store_name")
    check("карточка не падает без store_name", "Жалоба №" in complaints.card(bare))
    await complaints.resolve(cid2, STAFF_TG, "убрано")

    # --- обход
    checkup_id = await checkups.create(STAFF_TG, store_id)
    for status in ("ok", "ok", "replaced", "empty", "skipped"):
        await checkups.add_item(checkup_id, tester_id, status)
    await checkups.finish(checkup_id)
    summary = await checkups.summary(checkup_id)
    check("сводка обхода корректна", "Всего осмотрено: 5" in summary and "Норма: 2" in summary)
    check("обход сегодня зафиксирован",
          await checkups.has_today(STAFF_TG, store_id))
    row = await db.fetchone("SELECT day FROM checkups WHERE id = ?", (checkup_id,))
    check("день обхода = сегодня", row["day"] == date.today().isoformat())

    # --- управление доступом (сотрудники/админы)
    await users.promote_employee(999, store_id, "Новый Сотрудник")
    e999 = await users.get(999)
    check("сотрудник добавлен напрямую (без старта бота)",
          e999["role"] == "employee" and e999["store_id"] == store_id)
    await users.promote_admin(888, "Второй Админ")
    check("админ добавлен напрямую", (await users.get(888))["role"] == "admin")
    await users.demote_to_customer(999)
    e999 = await users.get(999)
    check("сотрудник снят с роли",
          e999["role"] == "customer" and e999["store_id"] is None)
    emps = await users.store_employees(store_id)
    check("список сотрудников магазина корректен",
          any(x["tg_id"] == STAFF_TG for x in emps) and all(x["tg_id"] != 999 for x in emps))
    check("список админов из БД",
          any(x["tg_id"] == ADMIN_TG for x in await users.db_admins()))

    # --- маршрутизация уведомлений: задачи только сотрудникам магазина
    emp_recipients = await notifier.store_employee_ids(store_id)
    check("задача о жалобе уходит только сотрудникам магазина",
          emp_recipients == {STAFF_TG})
    adm_recipients = await notifier.all_admin_ids()
    check("страховочный список админов корректен",
          ADMIN_TG in adm_recipients and 888 in adm_recipients
          and STAFF_TG not in adm_recipients)

    # --- QR
    link = qr.deep_link("test_bot", code)
    check("deep link сформирован", link == f"https://t.me/test_bot?start=c-{code}")
    png = qr.qr_png_bytes(link)
    check("PNG не пустой и валидный", png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 500)
    store = await db.fetchone("SELECT * FROM stores WHERE id = ?", (store_id,))
    testers = await db.fetchall("SELECT * FROM testers WHERE store_id = ?", (store_id,))
    zip_bytes = qr.store_zip(store, testers, "test_bot")
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    check("ZIP валиден и содержит файлы",
          zf.testzip() is None and f"{code}.png" in zf.namelist() and "labels.txt" in zf.namelist())
    html_doc = qr.printable_html(store, testers, "test_bot")
    check("печатный HTML содержит QR и этикетки",
          "base64," in html_doc and "Dior" in html_doc and code in html_doc)

    # --- уникальность кодов тестеров
    seen = set()
    dup = False
    for _ in range(200):
        c2 = qr.gen_tester_code()
        if c2 in seen:
            dup = True
        seen.add(c2)
    check("генерация кодов без коллизий (200 шт.)", not dup)

    print("\nВсе проверки пройдены ✅")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        if os.path.exists("smoke_test.db"):
            try:
                os.remove("smoke_test.db")
            except PermissionError:
                print("⚠️ Не удалось удалить smoke_test.db (файл занят) — удалите вручную.")
