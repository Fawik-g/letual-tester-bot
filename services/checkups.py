"""Обходы магазина: создание, отметки, сводка."""
from datetime import date

import db
from constants import CHECK_LABELS, PROBLEM_STATUSES


async def active_testers(store_id: int) -> list[dict]:
    return await db.fetchall(
        "SELECT * FROM testers WHERE store_id = ? AND is_active = 1 ORDER BY brand, product",
        (store_id,),
    )


async def create(employee_tg_id: int, store_id: int) -> int:
    return await db.execute(
        "INSERT INTO checkups (employee_tg_id, store_id, day) VALUES (?, ?, ?)",
        (employee_tg_id, store_id, date.today().isoformat()),
    )


async def add_item(checkup_id: int, tester_id: int, status: str) -> None:
    await db.execute(
        "INSERT INTO checkup_items (checkup_id, tester_id, status) VALUES (?, ?, ?)",
        (checkup_id, tester_id, status),
    )


async def finish(checkup_id: int) -> None:
    await db.execute(
        "UPDATE checkups SET finished_at = datetime('now', 'localtime') WHERE id = ?",
        (checkup_id,),
    )


async def has_today(tg_id: int, store_id: int) -> bool:
    row = await db.fetchone(
        "SELECT id FROM checkups WHERE employee_tg_id = ? AND store_id = ? AND day = ?",
        (tg_id, store_id, date.today().isoformat()),
    )
    return row is not None


async def summary(checkup_id: int) -> str:
    """Текстовая сводка по обходу."""
    rows = await db.fetchall(
        "SELECT status, COUNT(*) AS n FROM checkup_items WHERE checkup_id = ? GROUP BY status",
        (checkup_id,),
    )
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    if not total:
        return "Осмотренных тестеров нет."

    problems = sum(counts.get(s, 0) for s in PROBLEM_STATUSES)
    lines = [
        f"🏁 Обход завершён.",
        f"Всего осмотрено: {total}",
        f"{CHECK_LABELS['ok']}: {counts.get('ok', 0)}",
        f"{CHECK_LABELS['replaced']}: {counts.get('replaced', 0)}",
        f"⚠️ Проблемы: {problems}",
    ]
    for s in PROBLEM_STATUSES:
        if counts.get(s):
            lines.append(f"   {CHECK_LABELS[s]}: {counts[s]}")
    if counts.get("skipped"):
        lines.append(f"{CHECK_LABELS['skipped']}: {counts['skipped']}")
    return "\n".join(lines)
