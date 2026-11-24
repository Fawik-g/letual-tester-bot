"""Роль сотрудника: ежедневный обход тестеров и работа с жалобами."""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import keyboards as kb
import notifier
import services.checkups as checkups
import services.complaints as complaints
import services.users as users
from constants import CHECK_LABELS

router = Router()


class CheckupWalk(StatesGroup):
    walking = State()


class ResolveNote(StatesGroup):
    note = State()


async def _staff_user(event) -> dict | None:
    user = await users.get(event.from_user.id)
    return user if users.is_staff(user) else None


def _can_handle(user: dict, complaint: dict) -> bool:
    return user["role"] == "admin" or user["store_id"] == complaint["store_id"]


# ---------------------------------------------------------------- меню

@router.callback_query(F.data == "menu:checkup")
async def menu_checkup(cb: CallbackQuery, state: FSMContext):
    user = await _staff_user(cb)
    if not user:
        return await cb.answer("Нет доступа. Войдите как сотрудник: /staff", show_alert=True)
    await state.clear()
    if user["store_id"]:
        return await begin_checkup(cb, state, user["store_id"])
    # админ без магазина — выбирает магазин
    stores = await db.fetchall("SELECT * FROM stores ORDER BY name")
    if not stores:
        await cb.message.answer("Магазинов ещё нет — попросите админа добавить их в панели /admin.")
        return await cb.answer()
    b = InlineKeyboardBuilder()
    for s in stores:
        b.button(text=s["name"], callback_data=f"chk:start:{s['id']}")
    b.adjust(1)
    await cb.message.answer("Выберите магазин для обхода:", reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("chk:start:"))
async def chk_start(cb: CallbackQuery, state: FSMContext):
    user = await _staff_user(cb)
    if not user or user["role"] != "admin":
        return await cb.answer("Нет доступа", show_alert=True)
    store_id = int(cb.data.rsplit(":", 1)[1])
    await begin_checkup(cb, state, store_id)


async def begin_checkup(cb: CallbackQuery, state: FSMContext, store_id: int) -> None:
    testers = await checkups.active_testers(store_id)
    if not testers:
        await cb.message.answer("В этом магазине пока нет активных тестеров в базе.")
        await cb.answer()
        return
    open_cmps = await complaints.open_for_store(store_id)
    checkup_id = await checkups.create(cb.from_user.id, store_id)
    await state.set_state(CheckupWalk.walking)
    await state.set_data({
        "checkup_id": checkup_id,
        "store_id": store_id,
        "testers": [t["id"] for t in testers],
        "idx": 0,
        "card_msg_id": None,
    })
    prefix = ""
    if open_cmps:
        prefix = (f"⚠️ По магазину {len(open_cmps)} открытых жалоб — "
                  f"посмотрите их в разделе «Жалобы».\n\n")
    await cb.message.answer(prefix + "🚶 Обход начат. Отмечайте состояние каждого тестера.")
    await send_card(cb.bot, cb.from_user.id, state)
    await cb.answer()


async def send_card(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    idx, tester_ids = data["idx"], data["testers"]
    if idx >= len(tester_ids):
        return await finish_checkup(bot, chat_id, state)
    t = await db.fetchone("SELECT * FROM testers WHERE id = ?", (tester_ids[idx],))
    text = (f"🧪 [{idx + 1}/{len(tester_ids)}] {t['brand']} — {t['product'] or '—'}\n"
            f"📍 {t['location'] or '—'}")
    msg = await bot.send_message(chat_id, text, reply_markup=kb.checkup_buttons())
    await state.update_data(card_msg_id=msg.message_id)


async def record_and_next(cb: CallbackQuery, state: FSMContext, status: str) -> None:
    data = await state.get_data()
    if cb.message and cb.message.message_id != data.get("card_msg_id"):
        return await cb.answer("Это старая карточка — текущий тестер другой.", show_alert=True)
    await checkups.add_item(data["checkup_id"], data["testers"][data["idx"]], status)
    if cb.message:
        try:
            await cb.message.edit_text(
                cb.message.text + f"\n→ {CHECK_LABELS.get(status, status)}",
                reply_markup=None,
            )
        except Exception:
            pass
    await cb.answer("Записано ✅")
    data["idx"] += 1
    await state.update_data(idx=data["idx"])
    if data["idx"] >= len(data["testers"]):
        await finish_checkup(cb.bot, cb.from_user.id, state)
    else:
        await send_card(cb.bot, cb.from_user.id, state)


async def finish_checkup(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    await checkups.finish(data["checkup_id"])
    summary = await checkups.summary(data["checkup_id"])
    await state.clear()
    await bot.send_message(chat_id, summary)


# ---------------------------------------------------------------- обход: кнопки

@router.callback_query(CheckupWalk.walking, F.data.startswith("chk:ans:"))
async def chk_answer(cb: CallbackQuery, state: FSMContext):
    status = cb.data.split(":", 2)[2]
    if status == "bad":
        try:
            await cb.message.edit_reply_markup(reply_markup=kb.problem_buttons())
        except Exception:
            pass
        return await cb.answer()
    await record_and_next(cb, state, status)


@router.callback_query(CheckupWalk.walking, F.data.startswith("chk:bad:"))
async def chk_bad(cb: CallbackQuery, state: FSMContext):
    status = cb.data.split(":", 2)[2]
    await record_and_next(cb, state, status)


@router.callback_query(CheckupWalk.walking, F.data == "chk:back")
async def chk_back(cb: CallbackQuery):
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.checkup_buttons())
    except Exception:
        pass
    await cb.answer()


@router.callback_query(CheckupWalk.walking, F.data == "chk:stop")
async def chk_stop(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await finish_checkup(cb.bot, cb.from_user.id, state)


@router.callback_query(F.data.startswith("chk:"))
async def chk_stale(cb: CallbackQuery, state: FSMContext):
    """Кнопки от старого обхода (например, после перезапуска бота)."""
    if await state.get_state() == CheckupWalk.walking:
        return  # уже обработано специализированным хендлером выше
    await cb.answer("Обход уже не активен. Начните новый: /menu", show_alert=True)


# ---------------------------------------------------------------- жалобы

@router.callback_query(F.data == "menu:complaints")
async def menu_complaints(cb: CallbackQuery, state: FSMContext):
    user = await _staff_user(cb)
    if not user:
        return await cb.answer("Нет доступа. Войдите как сотрудник: /staff", show_alert=True)
    await state.clear()
    if user["store_id"]:
        return await list_complaints(cb, user["store_id"])
    stores = await db.fetchall("SELECT * FROM stores ORDER BY name")
    b = InlineKeyboardBuilder()
    for s in stores:
        b.button(text=s["name"], callback_data=f"cmp:list:{s['id']}")
    b.adjust(1)
    await cb.message.answer("Выберите магазин:", reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("cmp:list:"))
async def cmp_list(cb: CallbackQuery):
    user = await _staff_user(cb)
    if not user:
        return await cb.answer("Нет доступа", show_alert=True)
    await list_complaints(cb, int(cb.data.rsplit(":", 1)[1]))


async def list_complaints(cb: CallbackQuery, store_id: int) -> None:
    items = await complaints.open_for_store(store_id)
    if not items:
        await cb.message.answer("Открытых жалоб нет 🎉")
        return
    await cb.message.answer(f"📥 Открытых жалоб: {len(items)}")
    for c in items:
        markup = kb.complaint_actions(c["id"], c["status"])
        if c["photo_file_id"]:
            await cb.message.answer_photo(c["photo_file_id"],
                                          caption=complaints.card(c), reply_markup=markup)
        else:
            await cb.message.answer(complaints.card(c), reply_markup=markup)


async def refresh_card(cb: CallbackQuery, c: dict) -> None:
    text = complaints.card(c)
    markup = kb.complaint_actions(c["id"], c["status"])
    try:
        if cb.message.photo:
            await cb.message.edit_caption(caption=text, reply_markup=markup)
        else:
            await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("cmp:take:"))
async def cmp_take(cb: CallbackQuery):
    user = await _staff_user(cb)
    if not user:
        return await cb.answer("Нет доступа", show_alert=True)
    c = await complaints.get_with_context(int(cb.data.rsplit(":", 1)[1]))
    if not c:
        return await cb.answer("Жалоба не найдена", show_alert=True)
    if not _can_handle(user, c):
        return await cb.answer("Это жалоба другого магазина", show_alert=True)
    if c["status"] != "new":
        return await cb.answer("Уже в работе или решена")
    await complaints.take(c["id"], cb.from_user.id)
    c = await complaints.get_with_context(c["id"])
    await notifier.notify_taken(cb.bot, c, c["taken_by_name"])
    await refresh_card(cb, c)
    await cb.answer("Взято в работу ⏳")


@router.callback_query(F.data.startswith("cmp:done:"))
async def cmp_done(cb: CallbackQuery, state: FSMContext):
    user = await _staff_user(cb)
    if not user:
        return await cb.answer("Нет доступа", show_alert=True)
    c = await complaints.get_with_context(int(cb.data.rsplit(":", 1)[1]))
    if not c:
        return await cb.answer("Жалоба не найдена", show_alert=True)
    if not _can_handle(user, c):
        return await cb.answer("Это жалоба другого магазина", show_alert=True)
    if c["status"] == "resolved":
        return await cb.answer("Уже решена")
    await state.set_state(ResolveNote.note)
    await state.update_data(complaint_id=c["id"])
    await cb.message.answer(
        "🛠 Что сделано по жалобе? Ответьте текстом\n"
        "(например: «заменил тестер», «почистил флакон, долил»)\n\n"
        "Или нажмите «Без описания».",
        reply_markup=kb.skip_button("Без описания ➡️", "cmp:note_skip"),
    )
    await cb.answer()


@router.message(ResolveNote.note, F.text)
async def resolve_note_text(message: Message, state: FSMContext, bot: Bot):
    await do_resolve(message, state, bot, message.text.strip()[:500])


@router.callback_query(ResolveNote.note, F.data == "cmp:note_skip")
async def resolve_note_skip(cb: CallbackQuery, state: FSMContext, bot: Bot):
    await do_resolve(cb.message, state, bot, "")
    await cb.answer()


async def do_resolve(message: Message, state: FSMContext, bot: Bot, note: str) -> None:
    data = await state.get_data()
    complaint_id = data.get("complaint_id")
    c = await complaints.get_with_context(complaint_id) if complaint_id else None
    if not c:
        await state.clear()
        return await message.answer("Жалоба не найдена.")
    await complaints.resolve(c["id"], message.from_user.id, note)
    c = await complaints.get_with_context(c["id"])
    await notifier.notify_resolved(bot, c, c["resolved_by_name"])
    await state.clear()
    await message.answer(f"✅ Жалоба №{c['id']} закрыта.")
