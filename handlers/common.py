"""Общие обработчики: /start, меню ролей, жалоба покупателя, вход сотрудника."""
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import notifier
import services.complaints as complaints
import services.users as users
from constants import ISSUE_LABELS

router = Router()


class ComplaintForm(StatesGroup):
    issue = State()
    photo = State()
    comment = State()
    confirm = State()


class StaffInvite(StatesGroup):
    code = State()


# ---------------------------------------------------------------- меню/старт

async def _upsert_from(message: Message) -> None:
    u = message.from_user
    await users.upsert(u.id, u.full_name, u.username)


async def send_welcome(message: Message, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    user = await users.get(message.from_user.id)
    if users.is_admin(user, message.from_user.id):
        text = (f"Здравствуйте, {user['full_name']}! Вы вошли как администратор.\n\n"
                "🛠 Управление — в админ-панели.")
        await message.answer(text, reply_markup=kb.admin_menu())
    elif users.is_staff(user):
        store = user["store_id"]
        text = (f"Вы сотрудник. Доступные действия:\n\n"
                "🚶 Обход — пройдите по тестерам магазина и отметьте их состояние.\n"
                "📥 Жалобы — жалобы покупателей вашего магазина.")
        await message.answer(text, reply_markup=kb.staff_menu())
    else:
        await message.answer(
            "👋 Привет! Это бот контроля качества тестеров.\n\n"
            "Заметили пустой, грязный или неработающий тестер?\n"
            "Наведите камеру телефона на QR-код рядом с тестером — "
            "и сотрудники магазина сразу узнают о проблеме.\n\n"
            "Если вы сотрудник магазина — отправьте команду /staff."
        )


@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, command: CommandObject, state: FSMContext):
    await _upsert_from(message)
    await state.clear()
    payload = (command.args or "").strip()

    if payload == "staff":
        return await ask_invite(message, state)

    if payload.startswith("c-"):
        code = payload[2:]
        tester = await complaints.find_tester_by_code(code)
        if tester:
            return await start_complaint(message, state, tester)
        await message.answer(
            "😔 QR-код не распознан: тестер не найден в базе.\n"
            "Пожалуйста, сообщите об этом сотруднику магазина."
        )
        return

    await send_welcome(message)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await _upsert_from(message)
    await send_welcome(message, state)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await _upsert_from(message)
    await send_welcome(message, state)


# ---------------------------------------------------------------- сотрудник

@router.message(Command("staff"))
async def cmd_staff(message: Message, state: FSMContext):
    await _upsert_from(message)
    user = await users.get(message.from_user.id)
    if users.is_staff(user):
        return await send_welcome(message, state)
    await ask_invite(message, state)


async def ask_invite(message: Message, state: FSMContext) -> None:
    await state.set_state(StaffInvite.code)
    await message.answer(
        "🔑 Вход для сотрудников.\n\n"
        "Введите код приглашения магазина (его выдаёт администратор)."
    )


@router.message(StaffInvite.code, F.text)
async def staff_enter_code(message: Message, state: FSMContext):
    invite = await users.find_invite(message.text or "")
    if not invite:
        await message.answer("Код не найден или отключён. Попробуйте ещё раз или обратитесь к администратору.")
        return
    await users.set_staff(message.from_user.id, invite["store_id"])
    await state.clear()
    await message.answer(f"✅ Готово! Вы закреплены за магазином «{invite['store_name']}».")
    await send_welcome(message)


# ---------------------------------------------------------------- жалоба покупателя

async def start_complaint(message: Message, state: FSMContext, tester: dict) -> None:
    await state.set_state(ComplaintForm.issue)
    await state.set_data({"tester_id": tester["id"]})
    card = (
        f"🧪 {tester['brand']} — {tester['product'] or '—'}\n"
        f"📍 {tester['location'] or '—'}\n"
        f"🏬 {tester['store_name']}\n\n"
        "Что не так с тестером?"
    )
    await message.answer(card, reply_markup=kb.issue_buttons())


@router.callback_query(ComplaintForm.issue, F.data.startswith("cm:issue:"))
async def pick_issue(cb: CallbackQuery, state: FSMContext):
    issue = cb.data.split(":", 2)[2]
    await state.update_data(issue=issue)
    await state.set_state(ComplaintForm.photo)
    await cb.message.edit_text(
        "📷 Прикрепите фото тестера — так сотруднику будет проще понять проблему.\n\n"
        "Или нажмите «Без фото».",
        reply_markup=kb.skip_button("Без фото ➡️", "cm:photo_skip"),
    )
    await cb.answer()


@router.callback_query(ComplaintForm.photo, F.data == "cm:photo_skip")
async def photo_skip(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ComplaintForm.comment)
    await cb.message.edit_text(
        "💬 Опишите проблему своими словами или нажмите «Без комментария».",
        reply_markup=kb.skip_button("Без комментария ➡️", "cm:comment_skip"),
    )
    await cb.answer()


@router.message(ComplaintForm.photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(ComplaintForm.comment)
    await message.answer(
        "💬 Опишите проблему своими словами или нажмите «Без комментария».",
        reply_markup=kb.skip_button("Без комментария ➡️", "cm:comment_skip"),
    )


@router.message(ComplaintForm.photo)
async def photo_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте фото или нажмите «Без фото».")


async def show_confirm(message: Message, state: FSMContext) -> None:
    await state.set_state(ComplaintForm.confirm)
    data = await state.get_data()
    tester = await db_get_tester(data["tester_id"])
    lines = [
        "Проверьте жалобу перед отправкой:",
        "",
        f"🧪 {tester['brand']} — {tester['product'] or '—'}",
        f"📍 {tester['location'] or '—'}",
        f"🏬 {tester['store_name']}",
        f"❗ {ISSUE_LABELS.get(data.get('issue'), data.get('issue'))}",
    ]
    if data.get("photo_file_id"):
        lines.append("📷 Фото приложено")
    if data.get("comment"):
        lines.append(f"💬 {data['comment']}")
    await message.answer("\n".join(lines), reply_markup=kb.confirm_buttons())


async def db_get_tester(tester_id: int) -> dict:
    return await db.fetchone(
        """SELECT t.*, s.name AS store_name FROM testers t
           JOIN stores s ON s.id = t.store_id WHERE t.id = ?""",
        (tester_id,),
    )


@router.message(ComplaintForm.comment, F.text)
async def got_comment(message: Message, state: FSMContext):
    await state.update_data(comment=message.text.strip()[:1000])
    await show_confirm(message, state)


@router.callback_query(ComplaintForm.comment, F.data == "cm:comment_skip")
async def comment_skip(cb: CallbackQuery, state: FSMContext):
    await state.update_data(comment="")
    await show_confirm(cb.message, state)
    await cb.answer()


@router.callback_query(ComplaintForm.confirm, F.data == "cm:submit")
async def submit_complaint(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    complaint_id = await complaints.create(
        tester_id=data["tester_id"],
        customer_tg_id=cb.from_user.id,
        issue_type=data.get("issue", "other"),
        comment=data.get("comment", ""),
        photo_file_id=data.get("photo_file_id"),
    )
    full = await complaints.get_with_context(complaint_id)
    await notifier.notify_new(bot, full)
    await state.clear()
    await cb.message.edit_text(
        f"✅ Спасибо! Жалоба №{complaint_id} передана в магазин «{full['store_name']}».\n"
        "Сотрудники займутся тестером в ближайшее время."
    )
    await cb.answer()


@router.callback_query(ComplaintForm.confirm, F.data == "cm:cancel")
async def cancel_complaint(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Жалоба отменена. Если что-то не так с тестером — попробуйте ещё раз.")
    await cb.answer()
