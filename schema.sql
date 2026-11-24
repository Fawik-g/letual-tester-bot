-- Схема БД тестер-бота (SQLite)

CREATE TABLE IF NOT EXISTS stores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    address    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS testers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id   INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    code       TEXT NOT NULL UNIQUE,          -- короткий код в QR (deep link)
    brand      TEXT NOT NULL,
    product    TEXT NOT NULL DEFAULT '',
    location   TEXT NOT NULL DEFAULT '',      -- полка / зона / витрина
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_testers_store ON testers(store_id);

CREATE TABLE IF NOT EXISTS users (
    tg_id      INTEGER PRIMARY KEY,
    full_name  TEXT NOT NULL DEFAULT '',
    username   TEXT NOT NULL DEFAULT '',
    role       TEXT NOT NULL DEFAULT 'customer',  -- customer | employee | admin
    store_id   INTEGER REFERENCES stores(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_users_store ON users(store_id);

CREATE TABLE IF NOT EXISTS complaints (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tester_id      INTEGER NOT NULL REFERENCES testers(id) ON DELETE CASCADE,
    store_id       INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    customer_tg_id INTEGER,
    issue_type     TEXT NOT NULL,
    comment        TEXT NOT NULL DEFAULT '',
    photo_file_id  TEXT,
    status         TEXT NOT NULL DEFAULT 'new',  -- new | in_progress | resolved
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    taken_by       INTEGER REFERENCES users(tg_id),
    resolved_at    TEXT,
    resolved_by    INTEGER REFERENCES users(tg_id),
    resolution     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_complaints_store_status ON complaints(store_id, status);

CREATE TABLE IF NOT EXISTS checkups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_tg_id  INTEGER NOT NULL REFERENCES users(tg_id),
    store_id        INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    day             TEXT NOT NULL,            -- локальная дата YYYY-MM-DD (для напоминаний/статистики)
    started_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS checkup_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    checkup_id  INTEGER NOT NULL REFERENCES checkups(id) ON DELETE CASCADE,
    tester_id   INTEGER NOT NULL REFERENCES testers(id) ON DELETE CASCADE,
    status      TEXT NOT NULL,               -- ok | replaced | empty | dirty | broken | missing | skipped
    comment     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_checkup_items ON checkup_items(checkup_id);

CREATE TABLE IF NOT EXISTS invite_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL UNIQUE,
    store_id   INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
