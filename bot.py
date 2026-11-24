"""Точка входа: запуск бота в режиме long polling."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

import db
from config import BOT_TOKEN, PROXY_URL
from handlers import admin, common, employee
from scheduler import reminder_loop

log = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="staff", description="Вход для сотрудников"),
        BotCommand(command="admin", description="Админ-панель"),
    ])


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "Ошибка: BOT_TOKEN не задан.\n"
            "Скопируйте .env.example в .env, получите токен у @BotFather и укажите его."
        )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    await db.init()

    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
    bot = Bot(BOT_TOKEN, session=session)

    # Ранняя диагностика связи с Telegram — вместо длинного трейсбека
    try:
        await bot.get_me()
    except TelegramNetworkError as e:
        await db.close()
        raise SystemExit(
            f"Не удалось подключиться к api.telegram.org:\n  {e}\n\n"
            "Похоже, провайдер блокирует Telegram API.\n"
            "Решение: укажите PROXY_URL в .env (http/socks5-прокси) — см. README, раздел «Прокси».\n"
            "Или включите VPN на уровне всей системы и запустите бота без PROXY_URL."
        )

    dp = Dispatcher(storage=MemoryStorage())
    dp.startup.register(on_startup)
    dp.include_routers(common.router, employee.router, admin.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        """Любая ошибка в хендлере логируется и не роняет бота."""
        log.error("Ошибка в хендлере (update_id=%s):", event.update.update_id,
                  exc_info=event.exception)
        try:
            if event.update.callback_query:
                await event.update.callback_query.answer(
                    "⚠️ Произошла ошибка, попробуйте ещё раз", show_alert=True)
            elif event.update.message:
                await event.update.message.answer("⚠️ Произошла ошибка, попробуйте ещё раз")
        except Exception:
            pass
        return True  # ошибка обработана — поллинг продолжается

    reminder = asyncio.create_task(reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminder.cancel()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
