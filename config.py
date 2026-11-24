"""Настройки бота из переменных окружения (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "letual.db")
REMINDER_TIME = os.getenv("REMINDER_TIME", "10:00").strip()
# Прокси, если api.telegram.org заблокирован провайдером.
# Форматы: http://host:port, socks5://host:port, socks5://user:pass@host:port
PROXY_URL = os.getenv("PROXY_URL", "").strip()


def admin_ids() -> tuple[int, ...]:
    """Telegram ID админов из ADMIN_IDS (через запятую и/или пробел)."""
    raw = os.getenv("ADMIN_IDS", "")
    return tuple(int(x) for x in raw.replace(",", " ").split() if x.strip())
