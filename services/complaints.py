"""Жалобы покупателей: создание, статусы, карточки для сообщений."""
from datetime import datetime

import db
from constants import COMPLAINT_STATUS, ISSUE_LABELS


def fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d.%m %H:%M")
    except ValueError:
        return value


async def find_tester_by_code(code: str) -> dict | None:
    return await db.fetchone(
        """SELECT t.*, s.name AS store_name
           FROM testers t
           JOIN stores s ON s.id = t.store_id
           WHERE UPPER(t.code) = UPPER(?) AND t.is_active = 1""",
        (code,),
    )


async def create(tester_id: int, customer_tg_id: int, issue_type: str,
                 comment: str, photo_file_id: str | None) -> int:
    tester = await db.fetchone("SELECT store_id FROM testers WHERE id = ?", (tester_id,))
    return await db.execute(
        """INSERT INTO complaints (tester_id, store_id, customer_tg_id, issue_type, comment, photo_file_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tester_id, tester["store_id"], customer_tg_id, issue_type, comment, photo_file_id),
    )


async def get_with_context(complaint_id: int) -> dict | None:
    return await db.fetchone(
        """SELECT c.*,
                  t.brand, t.product, t.location, t.code AS tester_code,
                  s.name AS store_name,
                  (SELECT full_name FROM users WHERE tg_id = c.taken_by)   AS taken_by_name,
                  (SELECT full_name FROM users WHERE tg_id = c.resolved_by) AS resolved_by_name
           FROM complaints c
           JOIN testers t ON t.id = c.tester_id
           JOIN stores s  ON s.id = c.store_id
           WHERE c.id = ?""",
        (complaint_id,),
    )


async def open_for_store(store_id: int) -> list[dict]:
    return await db.fetchall(
        """SELECT c.*,
                  t.brand, t.product, t.location, t.code AS tester_code,
                  s.name AS store_name,
                  (SELECT full_name FROM users WHERE tg_id = c.taken_by) AS taken_by_name
           FROM complaints c
           JOIN testers t ON t.id = c.tester_id
           JOIN stores s ON s.id = c.store_id
           WHERE c.store_id = ? AND c.status != 'resolved'
           ORDER BY c.created_at""",
        (store_id,),
    )


async def take(complaint_id: int, tg_id: int) -> None:
    await db.execute(
        "UPDATE complaints SET status = 'in_progress', taken_by = ? WHERE id = ? AND status = 'new'",
        (tg_id, complaint_id),
    )


async def resolve(complaint_id: int, tg_id: int, resolution: str) -> None:
    await db.execute(
        """UPDATE complaints
           SET status = 'resolved',
               resolved_by = ?,
               resolved_at = datetime('now', 'localtime'),
               resolution = ?
           WHERE id = ?""",
        (tg_id, resolution, complaint_id),
    )


def card(c: dict, with_store: bool = True) -> str:
    """Текстовая карточка жалобы для сообщений."""
    parts = [f"🔴 Жалоба №{c['id']} — {COMPLAINT_STATUS.get(c['status'], c['status'])}"]
    if with_store and c.get("store_name"):
        parts.append(f"🏬 {c['store_name']}")
    parts.append(f"🧪 {c['brand']} — {c['product'] or '—'}")
    if c.get("location"):
        parts.append(f"📍 {c['location']}")
    parts.append(f"❗ {ISSUE_LABELS.get(c['issue_type'], c['issue_type'])}")
    if c["comment"]:
        parts.append(f"💬 {c['comment']}")
    parts.append(f"🕐 {fmt_dt(c['created_at'])}")
    if c["status"] == "in_progress" and c.get("taken_by_name"):
        parts.append(f"👤 В работе: {c['taken_by_name']}")
    if c["status"] == "resolved":
        who = c.get("resolved_by_name") or "сотрудник"
        parts.append(f"✅ Решена ({who}, {fmt_dt(c['resolved_at'])})")
        if c["resolution"]:
            parts.append(f"🛠 {c['resolution']}")
    return "\n".join(parts)
