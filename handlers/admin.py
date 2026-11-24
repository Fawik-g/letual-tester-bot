"""Админ-панель: магазины, тестеры, сотрудники, админы, инвайт-коды, QR-коды, статистика."""
import secrets

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, MessageOriginUser
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import keyboards as kb
import services.qr as qr
import services.users as users
from config import admin_ids
from constants import COMPLAINT_STATUS

router = Router()

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class StoreAdd(StatesGroup):
    name = State()
    address = State()


class TesterAdd(StatesGroup):
    brand = State()
    product = State()
    location = State()


class CsvImport(StatesGroup):
    waiting = State()


class EmpForward(StatesGroup):
    waiting = State()


class AdminForward(StatesGroup):
    waiting = State()


def forward_origin_user(message: Message):
    """Автор пересланного сообщения, если Telegram его не скрыл."""
    origin = getattr(message, "forward_origin", None)
    if isinstance(origin, MessageOriginUser):
        return origin.user
    return None


# ---------------------------------------------------------------- гварды

async def _require_admin(event) -> bool:
    user = await users.get(event.from_user.id)
    if not users.is_admin(user, event.from_user.id):
        if isinstance(event, CallbackQuery):
            await event.answer("Только для администраторов", show_alert=True)
        return False
    return True


# ---------------------------------------------------------------- вход

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not await _require_admin(message):
        return
    await state.clear()
    await message.answer("🛠 Админ-панель", reply_markup=kb.admin_panel())


@router.callback_query(F.data == "menu:admin")
async def menu_admin(cb: CallbackQuery, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.clear()
    await cb.message.answer("🛠 Админ-панель", reply_markup=kb.admin_panel())
    await cb.answer()


# ---------------------------------------------------------------- магазины

@router.callback_query(F.data == "adm:stores")
async def adm_stores(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    stores = await db.fetchall(
        """SELECT s.*, (SELECT COUNT(*) FROM testers WHERE store_id = s.id AND is_active = 1) AS testers
           FROM stores s ORDER BY s.name"""
    )
    b = InlineKeyboardBuilder()
    for s in stores:
        b.button(text=f"🏬 {s['name']} ({s['testers']} тестеров)", callback_data=f"stv:{s['id']}")
    b.button(text="➕ Добавить магазин", callback_data="adm:store_add")
    b.adjust(1)
    await cb.message.answer("🏬 Магазины:" if stores else "Магазинов пока нет.",
                            reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(F.data == "adm:store_add")
async def adm_store_add(cb: CallbackQuery, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.set_state(StoreAdd.name)
    await cb.message.answer("Введите название магазина (например: Лэтуаль — ТЦ «Атриум»):")
    await cb.answer()


@router.message(StoreAdd.name, F.text)
async def store_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip()[:200])
    await state.set_state(StoreAdd.address)
    await message.answer("Введите адрес магазина (или «-», чтобы пропустить):")


@router.message(StoreAdd.address, F.text)
async def store_address(message: Message, state: FSMContext):
    data = await state.get_data()
    address = "" if message.text.strip() == "-" else message.text.strip()[:300]
    store_id = await db.execute(
        "INSERT INTO stores (name, address) VALUES (?, ?)", (data["name"], address)
    )
    await state.clear()
    await show_store(message, store_id)


@router.callback_query(F.data.startswith("stv:"))
async def store_view(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    await show_store(cb.message, int(cb.data.rsplit(":", 1)[1]))
    await cb.answer()


async def show_store(message: Message, store_id: int) -> None:
    store = await db.fetchone("SELECT * FROM stores WHERE id = ?", (store_id,))
    if not store:
        await message.answer("Магазин не найден.")
        return
    testers = await db.fetchone(
        "SELECT COUNT(*) AS n FROM testers WHERE store_id = ? AND is_active = 1", (store_id,)
    )
    employees = await db.fetchall(
        "SELECT full_name FROM users WHERE role = 'employee' AND store_id = ?", (store_id,)
    )
    text = [
        f"🏬 {store['name']}",
        f"📍 {store['address'] or '—'}",
        f"🧪 Активных тестеров: {testers['n']}",
        f"👥 Сотрудники: " + (", ".join(e["full_name"] for e in employees) if employees else "не добавлены"),
    ]
    b = InlineKeyboardBuilder()
    b.button(text="🧪 Тестеры", callback_data=f"tst:list:{store_id}")
    b.button(text="➕ Добавить тестер", callback_data=f"tst:add:{store_id}")
    b.button(text="📥 Импорт тестеров списком", callback_data=f"tst:csv:{store_id}")
    b.button(text="👥 Сотрудники", callback_data=f"emp:s:{store_id}")
    b.button(text="🖨 QR-коды магазина", callback_data=f"qr:s:{store_id}")
    b.button(text="⬅️ К магазинам", callback_data="adm:stores")
    b.adjust(1)
    await message.answer("\n".join(text), reply_markup=b.as_markup())


# ---------------------------------------------------------------- тестеры

@router.callback_query(F.data.startswith("tst:list:"))
async def tst_list(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    await render_testers(cb.message, int(cb.data.rsplit(":", 1)[1]))
    await cb.answer()


async def render_testers(message: Message, store_id: int) -> None:
    testers = await db.fetchall(
        "SELECT * FROM testers WHERE store_id = ? ORDER BY brand, product", (store_id,)
    )
    b = InlineKeyboardBuilder()
    for t in testers:
        mark = "🟢" if t["is_active"] else "⚪️"
        label = f"{mark} {t['brand']} {t['product']} ({t['code']})"
        b.button(text=label[:60], callback_data=f"tst:tgl:{t['id']}")
    b.button(text="⬅️ К магазину", callback_data=f"stv:{store_id}")
    b.adjust(1)
    await message.answer(
        "🧪 Тестеры (нажмите, чтобы включить/выключить):",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("tst:tgl:"))
async def tst_toggle(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    tester_id = int(cb.data.rsplit(":", 1)[1])
    await db.execute(
        "UPDATE testers SET is_active = 1 - is_active WHERE id = ?", (tester_id,)
    )
    row = await db.fetchone("SELECT store_id FROM testers WHERE id = ?", (tester_id,))
    if row:
        await render_testers(cb.message, row["store_id"])
    await cb.answer("Статус переключён")


@router.callback_query(F.data.startswith("tst:add:"))
async def tst_add(cb: CallbackQuery, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.set_state(TesterAdd.brand)
    await state.update_data(store_id=int(cb.data.rsplit(":", 1)[1]))
    await cb.message.answer("Бренд тестера (например: Lancôme):")
    await cb.answer()


@router.message(TesterAdd.brand, F.text)
async def tester_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text.strip()[:100])
    await state.set_state(TesterAdd.product)
    await message.answer("Название продукта (например: La Vie Est Belle, 50 мл) или «-»:")


@router.message(TesterAdd.product, F.text)
async def tester_product(message: Message, state: FSMContext):
    product = "" if message.text.strip() == "-" else message.text.strip()[:150]
    await state.update_data(product=product)
    await state.set_state(TesterAdd.location)
    await message.answer("Где стоит тестер (например: полка 3, люкс-зона) или «-»:")


@router.message(TesterAdd.location, F.text)
async def tester_location(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    location = "" if message.text.strip() == "-" else message.text.strip()[:150]
    code = await gen_unique_code()
    tester_id = await db.execute(
        "INSERT INTO testers (store_id, code, brand, product, location) VALUES (?, ?, ?, ?, ?)",
        (data["store_id"], code, data["brand"], data["product"], location),
    )
    await state.clear()
    username = (await bot.me()).username
    await message.answer(
        f"✅ Тестер добавлен (№{tester_id}).\n"
        f"🧪 {data['brand']} — {data['product'] or '—'}\n"
        f"Код: {code}\n"
        f"Ссылка для QR: https://t.me/{username}?start=c-{code}\n\n"
        f"QR-коды для печати — в карточке магазина.",
        reply_markup=kb.skip_button("➕ Добавить ещё тестер", f"tst:add:{data['store_id']}"),
    )


async def gen_unique_code(n: int = 6) -> str:
    while True:
        code = qr.gen_tester_code(n)
        if not await db.fetchone("SELECT id FROM testers WHERE code = ?", (code,)):
            return code


@router.callback_query(F.data.startswith("tst:csv:"))
async def tst_csv(cb: CallbackQuery, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.set_state(CsvImport.waiting)
    await state.update_data(store_id=int(cb.data.rsplit(":", 1)[1]))
    await cb.message.answer(
        "📥 Импорт тестеров.\n\n"
        "Отправьте сообщение, в каждой строке один тестер в формате:\n"
        "Бренд;Продукт;Место\n\n"
        "Пример:\n"
        "Dior;J'adore, 50мл;Полка 3, люкс\n"
        "Chanel;Bleu de Chanel;Прикассовая зона\n\n"
        "Продукт и место можно опустить: Dior;;;Полка 1"
    )
    await cb.answer()


@router.message(CsvImport.waiting, F.text)
async def csv_import(message: Message, state: FSMContext):
    data = await state.get_data()
    store_id = data["store_id"]
    created, skipped = 0, 0
    for line in message.text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace("\t", ";").split(";")]
        brand = parts[0][:100] if parts else ""
        if not brand:
            skipped += 1
            continue
        product = parts[1][:150] if len(parts) > 1 else ""
        location = parts[2][:150] if len(parts) > 2 else ""
        code = await gen_unique_code()
        await db.execute(
            "INSERT INTO testers (store_id, code, brand, product, location) VALUES (?, ?, ?, ?, ?)",
            (store_id, code, brand, product, location),
        )
        created += 1
    await state.clear()
    await message.answer(f"✅ Импортировано тестеров: {created}"
                         + (f", пропущено строк: {skipped}" if skipped else ""))


# ---------------------------------------------------------------- инвайт-коды

@router.callback_query(F.data.startswith("inv:s:"))
async def inv_show(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    store_id = int(cb.data.rsplit(":", 1)[1])
    invites = await db.fetchall(
        "SELECT * FROM invite_codes WHERE store_id = ? AND is_active = 1 ORDER BY id DESC",
        (store_id,),
    )
    b = InlineKeyboardBuilder()
    for i in invites:
        b.button(text=f"🚫 Отключить {i['code']}", callback_data=f"inv:off:{i['id']}")
    b.button(text="➕ Новый код", callback_data=f"inv:new:{store_id}")
    b.button(text="⬅️ К магазину", callback_data=f"stv:{store_id}")
    b.adjust(1)
    codes = "\n".join(f"• {i['code']}" for i in invites) or "Активных кодов нет."
    await cb.message.answer(
        f"🎫 Инвайт-коды магазина.\n\n{codes}\n\n"
        "Сотрудник вводит код в боте по команде /staff и закрепляется за магазином.",
        reply_markup=b.as_markup(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("inv:new:"))
async def inv_new(cb: CallbackQuery, bot: Bot):
    if not await _require_admin(cb):
        return
    store_id = int(cb.data.rsplit(":", 1)[1])
    code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
    await db.execute("INSERT INTO invite_codes (code, store_id) VALUES (?, ?)", (code, store_id))
    username = (await bot.me()).username
    await cb.message.answer(
        f"🎫 Новый код: {code}\n\n"
        f"Передайте сотруднику ссылку и код:\n"
        f"1) Открыть бота: https://t.me/{username}?start=staff\n"
        f"2) Ввести код: {code}"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("inv:off:"))
async def inv_off(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    await db.execute("UPDATE invite_codes SET is_active = 0 WHERE id = ?",
                     (int(cb.data.rsplit(":", 1)[1]),))
    await cb.answer("Код отключён")


# ---------------------------------------------------------------- сотрудники

@router.callback_query(F.data.startswith("emp:s:"))
async def emp_show(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    await render_employees(cb.message, int(cb.data.rsplit(":", 1)[1]))
    await cb.answer()


async def render_employees(message: Message, store_id: int) -> None:
    store = await db.fetchone("SELECT * FROM stores WHERE id = ?", (store_id,))
    employees = await users.store_employees(store_id)
    lines = [f"👥 Сотрудники «{store['name']}»: {len(employees)}"]
    for e in employees:
        who = e["full_name"] + (f" (@{e['username']})" if e["username"] else "")
        lines.append(f"• {who}")
    if not employees:
        lines.append("Пока никого — добавьте первым.")

    b = InlineKeyboardBuilder()
    for e in employees:
        b.button(text=f"🚫 Убрать {e['full_name']}", callback_data=f"emp:rm:{e['tg_id']}")
    b.button(text="➕ Добавить сотрудника", callback_data=f"emp:add:{store_id}")
    b.button(text="⬅️ К магазину", callback_data=f"stv:{store_id}")
    b.adjust(1)
    await message.answer("\n".join(lines), reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("emp:rm:"))
async def emp_remove(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    tg_id = int(cb.data.rsplit(":", 1)[1])
    target = await users.get(tg_id)
    if not target or target["role"] != "employee":
        return await cb.answer("Уже не сотрудник")
    store_id = target["store_id"]
    await users.demote_to_customer(tg_id)
    if store_id:
        await render_employees(cb.message, store_id)
    await cb.answer(f"Убран: {target['full_name']}")


@router.callback_query(F.data.startswith("emp:add:"))
async def emp_add_menu(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    store_id = int(cb.data.rsplit(":", 1)[1])
    b = InlineKeyboardBuilder()
    b.button(text="🎫 Инвайт-код (для передачи на месте)", callback_data=f"inv:s:{store_id}")
    b.button(text="📤 Переслать сообщение сотрудника", callback_data=f"emp:fwd:{store_id}")
    b.button(text="⬅️ Назад", callback_data=f"emp:s:{store_id}")
    b.adjust(1)
    await cb.message.answer(
        "➕ Как добавить сотрудника?\n\n"
        "🎫 Инвайт-код — сгенерируйте код и передайте человеку (ссылка + код).\n"
        "📤 Переслать сообщение — перешлите сюда любое сообщение от этого человека, "
        "бот сам определит автора. Попросите человека сначала нажать /start у бота.",
        reply_markup=b.as_markup(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("emp:fwd:"))
async def emp_fwd_start(cb: CallbackQuery, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.set_state(EmpForward.waiting)
    await state.update_data(store_id=int(cb.data.rsplit(":", 1)[1]))
    await cb.message.answer(
        "📤 Перешлите сообщение от будущего сотрудника.\n\n"
        "Не удаётся (автор скрыт)? Пришлите его Telegram ID цифрами."
    )
    await cb.answer()


@router.message(EmpForward.waiting)
async def emp_forward(message: Message, state: FSMContext):
    data = await state.get_data()
    store_id = data.get("store_id")
    if not store_id:
        await state.clear()
        return

    origin = forward_origin_user(message)
    text = (message.text or "").strip()
    if origin:
        tg_id, name, username = origin.id, origin.full_name, origin.username
    elif text.isdigit() and 3 <= len(text) <= 15:
        tg_id, name, username = int(text), "", None
    else:
        return await message.answer(
            "Автор пересылки скрыт настройками приватности Telegram.\n"
            "Пришлите Telegram ID цифрами (узнать: @userinfobot) — или используйте инвайт-код."
        )

    existing = await users.get(tg_id)
    if existing and existing["role"] == "admin":
        return await message.answer("Этот человек уже админ — сотрудником его делать не нужно.")

    moved = bool(existing and existing["role"] == "employee" and existing["store_id"] != store_id)
    await users.promote_employee(tg_id, store_id, name, username)
    store = await db.fetchone("SELECT name FROM stores WHERE id = ?", (store_id,))
    await state.clear()
    who = name or (existing or {}).get("full_name") or f"ID {tg_id}"
    await message.answer(
        f"✅ {who} — сотрудник магазина «{store['name']}»"
        + (" (переназначен с другого магазина)" if moved else "") + ".\n"
        f"Попросите его открыть бота и нажать /start — появится меню обхода и жалоб."
    )


# ---------------------------------------------------------------- админы

@router.callback_query(F.data == "adm:admins")
async def adm_admins(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    await render_admins(cb.message)
    await cb.answer()


async def render_admins(message: Message) -> None:
    env_ids = set(admin_ids())
    admins = await users.db_admins()
    known = {a["tg_id"] for a in admins}

    lines = ["👑 Админы:"]
    b = InlineKeyboardBuilder()
    for a in admins:
        who = a["full_name"] + (f" (@{a['username']})" if a["username"] else "")
        if a["tg_id"] in env_ids:
            lines.append(f"• {who} — 🔒 задан в .env")
        else:
            lines.append(f"• {who}")
            b.button(text=f"🚫 Убрать {a['full_name']}", callback_data=f"adm:rmadmin:{a['tg_id']}")
    for tg_id in env_ids - known:
        lines.append(f"• ID {tg_id} — 🔒 из .env (ещё не открывал бота)")

    b.button(text="➕ Добавить админа", callback_data="adm:addadmin")
    b.adjust(1)
    await message.answer("\n".join(lines), reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("adm:rmadmin:"))
async def adm_rmadmin(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    tg_id = int(cb.data.rsplit(":", 1)[1])
    if tg_id in admin_ids():
        return await cb.answer("Этот админ задан в .env — уберите его там", show_alert=True)
    if tg_id == cb.from_user.id:
        return await cb.answer("Нельзя снять права с себя", show_alert=True)
    target = await users.get(tg_id)
    if not target or target["role"] != "admin":
        return await cb.answer("Он уже не админ")
    await users.demote_to_customer(tg_id)
    await render_admins(cb.message)
    await cb.answer(f"Снят: {target['full_name']}")


@router.callback_query(F.data == "adm:addadmin")
async def adm_addadmin(cb: CallbackQuery, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.set_state(AdminForward.waiting)
    await cb.message.answer(
        "📤 Перешлите сообщение от будущего админа.\n\n"
        "Не удаётся (автор скрыт)? Пришлите его Telegram ID цифрами."
    )
    await cb.answer()


@router.message(AdminForward.waiting)
async def adm_forward(message: Message, state: FSMContext):
    origin = forward_origin_user(message)
    text = (message.text or "").strip()
    if origin:
        tg_id, name, username = origin.id, origin.full_name, origin.username
    elif text.isdigit() and 3 <= len(text) <= 15:
        tg_id, name, username = int(text), "", None
    else:
        return await message.answer(
            "Автор пересылки скрыт настройками приватности Telegram.\n"
            "Пришлите Telegram ID цифрами (узнать: @userinfobot)."
        )
    await users.promote_admin(tg_id, name, username)
    await state.clear()
    who = name or f"ID {tg_id}"
    await message.answer(
        f"✅ {who} теперь админ. Попросите его открыть бота и нажать /start — "
        f"появится кнопка «Админ-панель» (или команда /admin)."
    )


# ---------------------------------------------------------------- QR

@router.callback_query(F.data.startswith("qr:s:"))
async def qr_store(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    store_id = int(cb.data.rsplit(":", 1)[1])
    store = await db.fetchone("SELECT * FROM stores WHERE id = ?", (store_id,))
    testers = await db.fetchall(
        "SELECT * FROM testers WHERE store_id = ? AND is_active = 1 ORDER BY brand, product",
        (store_id,),
    )
    if not testers:
        return await cb.answer("Сначала добавьте тестеры в этот магазин", show_alert=True)
    username = (await cb.bot.me()).username
    stem = qr.file_stem(store)
    zip_bytes = qr.store_zip(store, testers, username)
    html_bytes = qr.printable_html(store, testers, username).encode("utf-8")
    await cb.message.answer_document(
        BufferedInputFile(zip_bytes, filename=f"{stem}.zip"),
        caption=f"🖨 QR-коды: {len(testers)} шт. (PNG + labels.txt со ссылками)",
    )
    await cb.message.answer_document(
        BufferedInputFile(html_bytes, filename=f"{stem}.html"),
        caption="📄 Печатный лист: откройте в браузере и распечатайте (Ctrl+P). "
                "Карточки вырежьте и положите рядом с тестерами.",
    )
    await cb.answer()


# ---------------------------------------------------------------- статистика

@router.callback_query(F.data == "adm:stats")
async def adm_stats(cb: CallbackQuery):
    if not await _require_admin(cb):
        return
    await cb.message.answer(await build_stats())
    await cb.answer()


async def build_stats() -> str:
    rows = await db.fetchall(
        """SELECT s.name,
                  COUNT(*) AS total,
                  SUM(c.status != 'resolved') AS open_cnt,
                  SUM(c.status = 'resolved') AS resolved_cnt,
                  AVG(CASE WHEN c.resolved_at IS NOT NULL
                      THEN (julianday(c.resolved_at) - julianday(c.created_at)) * 24 END) AS avg_h
           FROM complaints c
           JOIN stores s ON s.id = c.store_id
           WHERE c.created_at >= datetime('now', 'localtime', '-7 days')
           GROUP BY s.id
           ORDER BY total DESC"""
    )
    total_all = sum(r["total"] for r in rows)
    lines = [f"📊 Статистика за 7 дней", "", f"Жалоб всего: {total_all}"]
    if rows:
        for r in rows:
            avg = f", ср. решение {r['avg_h']:.1f} ч" if r["avg_h"] is not None else ""
            lines.append(
                f"• {r['name']}: {r['total']} жалоб "
                f"(открыто {r['open_cnt']}, решено {r['resolved_cnt']}{avg})"
            )
    else:
        lines.append("Жалоб пока не было.")

    checkup_rows = await db.fetchall(
        """SELECT s.name, COUNT(*) AS n
           FROM checkups ck JOIN stores s ON s.id = ck.store_id
           WHERE ck.day >= date('now', 'localtime', '-7 days')
           GROUP BY s.id ORDER BY n DESC"""
    )
    lines += ["", f"Обходы за 7 дней: {sum(r['n'] for r in checkup_rows)}"]
    for r in checkup_rows:
        lines.append(f"• {r['name']}: {r['n']}")

    today = await db.fetchall(
        """SELECT DISTINCT s.name FROM checkups ck
           JOIN stores s ON s.id = ck.store_id
           WHERE ck.day = date('now', 'localtime')"""
    )
    done = {r["name"] for r in today}
    stores = await db.fetchall("SELECT name FROM stores ORDER BY name")
    marks = ", ".join(f"{'✅' if s['name'] in done else '❌'} {s['name']}" for s in stores)
    lines += ["", f"Обход сегодня: {marks or '—'}"]

    open_by_status = await db.fetchall(
        "SELECT status, COUNT(*) AS n FROM complaints GROUP BY status"
    )
    if open_by_status:
        lines += ["", "Все жалобы (за всё время): " + ", ".join(
            f"{COMPLAINT_STATUS.get(r['status'], r['status'])}: {r['n']}" for r in open_by_status
        )]
    return "\n".join(lines)
