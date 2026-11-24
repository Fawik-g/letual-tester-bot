"""Инлайн-клавиатуры бота."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from constants import ISSUE_TYPES, ISSUE_LABELS, PROBLEM_TYPES, PROBLEM_LABELS


def _b() -> InlineKeyboardBuilder:
    return InlineKeyboardBuilder()


def staff_menu() -> InlineKeyboardMarkup:
    b = _b()
    b.button(text="🚶 Начать обход", callback_data="menu:checkup")
    b.button(text="📥 Жалобы магазина", callback_data="menu:complaints")
    b.adjust(1)
    return b.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    b = _b()
    b.button(text="🚶 Начать обход", callback_data="menu:checkup")
    b.button(text="📥 Жалобы", callback_data="menu:complaints")
    b.button(text="🛠 Админ-панель", callback_data="menu:admin")
    b.adjust(1)
    return b.as_markup()


def admin_panel() -> InlineKeyboardMarkup:
    b = _b()
    b.button(text="🏬 Магазины", callback_data="adm:stores")
    b.button(text="👑 Админы", callback_data="adm:admins")
    b.button(text="📊 Статистика", callback_data="adm:stats")
    b.adjust(1)
    return b.as_markup()


def issue_buttons() -> InlineKeyboardMarkup:
    b = _b()
    for it in ISSUE_TYPES:
        b.button(text=ISSUE_LABELS[it], callback_data=f"cm:issue:{it}")
    b.adjust(1)
    return b.as_markup()


def skip_button(text: str, callback_data: str) -> InlineKeyboardMarkup:
    b = _b()
    b.button(text=text, callback_data=callback_data)
    return b.as_markup()


def confirm_buttons() -> InlineKeyboardMarkup:
    b = _b()
    b.button(text="✅ Отправить", callback_data="cm:submit")
    b.button(text="❌ Отмена", callback_data="cm:cancel")
    b.adjust(2)
    return b.as_markup()


def checkup_buttons() -> InlineKeyboardMarkup:
    b = _b()
    b.button(text="✅ ОК", callback_data="chk:ans:ok")
    b.button(text="🔄 Заменён", callback_data="chk:ans:replaced")
    b.button(text="⚠️ Проблема", callback_data="chk:ans:bad")
    b.button(text="⏭ Пропустить", callback_data="chk:ans:skip")
    b.adjust(2, 1, 1)
    b.button(text="⏹ Завершить обход", callback_data="chk:stop")
    return b.as_markup()


def problem_buttons() -> InlineKeyboardMarkup:
    b = _b()
    for p in PROBLEM_TYPES:
        b.button(text=PROBLEM_LABELS[p], callback_data=f"chk:bad:{p}")
    b.adjust(1)
    b.button(text="⬅️ Назад", callback_data="chk:back")
    return b.as_markup()


def complaint_actions(complaint_id: int, status: str) -> InlineKeyboardMarkup | None:
    b = _b()
    if status == "new":
        b.button(text="⏳ Взять в работу", callback_data=f"cmp:take:{complaint_id}")
    if status in ("new", "in_progress"):
        b.button(text="✅ Решено", callback_data=f"cmp:done:{complaint_id}")
    if not b.buttons:
        return None
    b.adjust(1)
    return b.as_markup()
