"""Работа с пользователями: роли, привязка к магазину, инвайт-коды."""
import db
from config import admin_ids


async def upsert(tg_id: int, full_name: str, username: str | None) -> None:
    """Создать/обновить профиль, не затирая роль и магазин.
    Админам из ADMIN_IDS сразу проставляется роль admin."""
    username = username or ""
    if tg_id in admin_ids():
        await db.execute(
            """INSERT INTO users (tg_id, full_name, username, role)
               VALUES (?, ?, ?, 'admin')
               ON CONFLICT(tg_id) DO UPDATE
               SET full_name = excluded.full_name,
                   username = excluded.username,
                   role = 'admin'""",
            (tg_id, full_name, username),
        )
    else:
        await db.execute(
            """INSERT INTO users (tg_id, full_name, username)
               VALUES (?, ?, ?)
               ON CONFLICT(tg_id) DO UPDATE
               SET full_name = excluded.full_name,
                   username = excluded.username""",
            (tg_id, full_name, username),
        )


async def get(tg_id: int) -> dict | None:
    return await db.fetchone("SELECT * FROM users WHERE tg_id = ?", (tg_id,))


def is_admin(user: dict | None, tg_id: int) -> bool:
    return bool(user and user["role"] == "admin") or tg_id in admin_ids()


def is_staff(user: dict | None) -> bool:
    return bool(user and user["role"] in ("employee", "admin"))


async def find_invite(code: str) -> dict | None:
    """Инвайт-код с названием магазина."""
    return await db.fetchone(
        """SELECT i.*, s.name AS store_name
           FROM invite_codes i
           JOIN stores s ON s.id = i.store_id
           WHERE UPPER(i.code) = UPPER(?) AND i.is_active = 1""",
        (code.strip(),),
    )


async def set_staff(tg_id: int, store_id: int) -> None:
    await db.execute(
        "UPDATE users SET role = 'employee', store_id = ? WHERE tg_id = ?",
        (store_id, tg_id),
    )


async def store_employees(store_id: int) -> list[dict]:
    return await db.fetchall(
        "SELECT tg_id, full_name, username FROM users "
        "WHERE role = 'employee' AND store_id = ? ORDER BY full_name",
        (store_id,),
    )


async def db_admins() -> list[dict]:
    return await db.fetchall(
        "SELECT tg_id, full_name, username FROM users WHERE role = 'admin' ORDER BY full_name"
    )


async def promote_employee(tg_id: int, store_id: int,
                           full_name: str = "", username: str | None = None) -> None:
    """Сделать сотрудником магазина (создать профиль, если человек ещё не открывал бота)."""
    if await get(tg_id):
        await db.execute(
            "UPDATE users SET role = 'employee', store_id = ? WHERE tg_id = ?",
            (store_id, tg_id),
        )
    else:
        await db.execute(
            "INSERT INTO users (tg_id, full_name, username, role, store_id) "
            "VALUES (?, ?, ?, 'employee', ?)",
            (tg_id, full_name or f"ID {tg_id}", username or "", store_id),
        )


async def promote_admin(tg_id: int, full_name: str = "",
                        username: str | None = None) -> None:
    if await get(tg_id):
        await db.execute("UPDATE users SET role = 'admin' WHERE tg_id = ?", (tg_id,))
    else:
        await db.execute(
            "INSERT INTO users (tg_id, full_name, username, role) VALUES (?, ?, ?, 'admin')",
            (tg_id, full_name or f"ID {tg_id}", username or ""),
        )


async def demote_to_customer(tg_id: int) -> None:
    """Снять роль (сотрудник/админ) — человек снова просто покупатель."""
    await db.execute(
        "UPDATE users SET role = 'customer', store_id = NULL WHERE tg_id = ?",
        (tg_id,),
    )
