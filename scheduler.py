"""Фоновая задача: ежедневное напоминание сотрудникам про обход."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

import db
import services.checkups as checkups
from config import REMINDER_TIME

log = logging.getLogger(__name__)

_loop_sleep = 30  # секунд


def _parse_reminder_time() -> tuple[int, int]:
    try:
        hh, mm = REMINDER_TIME.split(":")
        return int(hh), int(mm)
    except ValueError:
        log.warning("REMINDER_TIME=%r не в формате ЧЧ:ММ, напоминания отключены", REMINDER_TIME)
        return -1, -1


async def reminder_loop(bot: Bot) -> None:
    hh, mm = _parse_reminder_time()
    sent_today: set[int] = set()
    current_day = None

    while True:
        now = datetime.now()
        if now.date() != current_day:
            current_day = now.date()
            sent_today.clear()

        if (now.hour, now.minute) == (hh, mm):
            employees = await users_all_employees()
            for e in employees:
                if e["tg_id"] in sent_today or not e["store_id"]:
                    continue
                if not await checkups.has_today(e["tg_id"], e["store_id"]):
                    sent_today.add(e["tg_id"])
                    try:
                        await bot.send_message(
                            e["tg_id"],
                            "🚶 Доброе утро! Напоминаем: сегодня нужно пройти обход тестеров.\n"
                            "Меню → «Начать обход» или /menu",
                        )
                    except Exception as err:  # сотрудник мог заблокировать бота
                        log.warning("Напоминание не доставлено %s: %s", e["tg_id"], err)

        await asyncio.sleep(_loop_sleep)


async def users_all_employees() -> list[dict]:
    return await db.fetchall("SELECT tg_id, store_id FROM users WHERE role = 'employee'")
