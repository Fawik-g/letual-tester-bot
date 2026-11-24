"""Уведомления о жалобах: задачи сотрудникам магазина."""
import logging

from aiogram import Bot

import db
import services.complaints as complaints
from config import admin_ids
from keyboards import complaint_actions

log = logging.getLogger(__name__)


async def store_employee_ids(store_id: int, exclude: int | None = None) -> set[int]:
    """Сотрудники конкретного магазина (без админов)."""
    rows = await db.fetchall(
        "SELECT tg_id FROM users WHERE role = 'employee' AND store_id = ?",
        (store_id,),
    )
    ids = {r["tg_id"] for r in rows}
    if exclude:
        ids.discard(exclude)
    return ids


async def all_admin_ids(exclude: int | None = None) -> set[int]:
    """Все админы: из БД и из ADMIN_IDS (.env)."""
    rows = await db.fetchall("SELECT tg_id FROM users WHERE role = 'admin'")
    ids = {r["tg_id"] for r in rows} | set(admin_ids())
    if exclude:
        ids.discard(exclude)
    return ids


async def _safe_send(bot: Bot, chat_id: int, text: str, markup=None, photo: str | None = None) -> None:
    try:
        if photo:
            await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, reply_markup=markup)
    except Exception as e:  # пользователь мог заблокировать бота
        log.warning("Не доставлено %s: %s", chat_id, e)


async def notify_new(bot: Bot, c: dict) -> None:
    """Задача о новой жалобе — сотрудникам магазина.
    Если сотрудников нет — страховочная доставка админам, чтобы жалоба не потерялась."""
    card = complaints.card(c, with_store=True)
    markup = complaint_actions(c["id"], c["status"])

    recipients = await store_employee_ids(c["store_id"])
    if recipients:
        text = f"📋 ЗАДАЧА: проверьте тестер в магазине «{c['store_name']}»\n\n{card}"
        for uid in recipients:
            await _safe_send(bot, uid, text, markup, c["photo_file_id"])
        return

    text = (f"⚠️ В магазине «{c['store_name']}» не назначен ни один сотрудник — "
            f"жалоба доставлена админам.\n"
            f"Назначьте: /admin → Магазины → магазин → 👥 Сотрудники.\n\n{card}")
    for uid in await all_admin_ids():
        await _safe_send(bot, uid, text, markup, c["photo_file_id"])


async def notify_taken(bot: Bot, c: dict, taken_by_name: str) -> None:
    text = (f"⏳ Жалоба №{c['id']} («{c['brand']}», {c['store_name']}) "
            f"взята в работу: {taken_by_name}")
    for uid in await store_employee_ids(c["store_id"], exclude=c["taken_by"]):
        await _safe_send(bot, uid, text)


async def notify_resolved(bot: Bot, c: dict, resolved_by_name: str) -> None:
    text = (f"✅ Жалоба №{c['id']} («{c['brand']}», {c['store_name']}) решена: {resolved_by_name}"
            + (f"\n🛠 {c['resolution']}" if c["resolution"] else ""))
    for uid in await store_employee_ids(c["store_id"], exclude=c["resolved_by"]):
        await _safe_send(bot, uid, text)

    # Покупателю, если он доступен
    if c["customer_tg_id"]:
        customer_text = (f"✅ Ваша жалоба №{c['id']} решена — тестер «{c['brand']}» "
                         f"в магазине «{c['store_name']}» приведён в порядок.")
        if c["resolution"]:
            customer_text += f"\n🛠 {c['resolution']}"
        await _safe_send(bot, c["customer_tg_id"], customer_text)
