"""Общие текстовые константы и статусы."""

# Типы проблем в жалобе покупателя
ISSUE_LABELS = {
    "empty": "🕳 Пустой",
    "dirty": "🧴 Загрязнён / неаккуратен",
    "broken": "🔧 Не работает помпа/распылитель",
    "spoiled": "🤢 Испорчен (запах/цвет)",
    "missing": "❓ Нет на месте",
    "other": "✏️ Другое",
}
ISSUE_TYPES = list(ISSUE_LABELS)

# Типы проблем при обходе (подменю «Проблема»)
PROBLEM_LABELS = {
    "empty": "🕳 Пустой",
    "dirty": "🧴 Загрязнён",
    "broken": "🔧 Сломан",
    "missing": "❓ Нет на месте",
}
PROBLEM_TYPES = list(PROBLEM_LABELS)

# Статусы осмотра тестера при обходе
CHECK_LABELS = {
    "ok": "✅ Норма",
    "replaced": "🔄 Тестер заменён",
    "empty": "🕳 Пустой",
    "dirty": "🧴 Загрязнён",
    "broken": "🔧 Сломан",
    "missing": "❓ Нет на месте",
    "skipped": "⏭ Пропущен",
}
PROBLEM_STATUSES = ("empty", "dirty", "broken", "missing")

# Статусы жалоб
COMPLAINT_STATUS = {
    "new": "🆕 Новая",
    "in_progress": "⏳ В работе",
    "resolved": "✅ Решена",
}
