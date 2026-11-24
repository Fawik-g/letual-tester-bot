"""Единое подключение к SQLite (aiosqlite) и простые хелперы."""
from pathlib import Path

import aiosqlite

from config import DB_PATH

_SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")

_conn: aiosqlite.Connection | None = None


async def init() -> aiosqlite.Connection:
    """Открыть соединение и создать таблицы, если их ещё нет."""
    global _conn
    _conn = await aiosqlite.connect(DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA foreign_keys = ON")
    await _conn.executescript(_SCHEMA)
    await _conn.commit()
    return _conn


def conn() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("База не инициализирована: сначала вызовите db.init()")
    return _conn


async def fetchall(query: str, params: tuple = ()) -> list[dict]:
    async with conn().execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def fetchone(query: str, params: tuple = ()) -> dict | None:
    async with conn().execute(query, params) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def execute(query: str, params: tuple = ()) -> int:
    """Выполнить запрос и вернуть lastrowid."""
    cur = await conn().execute(query, params)
    await _conn.commit()
    return cur.lastrowid


async def close() -> None:
    """Закрыть соединение (поток aiosqlite не daemon — без этого процесс не завершится)."""
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None
