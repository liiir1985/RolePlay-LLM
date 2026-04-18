import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "annotation.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS records (
    id         TEXT PRIMARY KEY,
    type       TEXT,
    name       TEXT,
    timestamp  TEXT,
    depth      INTEGER,
    input      TEXT,
    output     TEXT,
    metadata   TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS annotation_schemas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_fields (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_id INTEGER NOT NULL REFERENCES annotation_schemas(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    label     TEXT NOT NULL,
    type      TEXT NOT NULL,
    options   TEXT,
    order_idx INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS queues (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    schema_id  INTEGER NOT NULL REFERENCES annotation_schemas(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS queue_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id  INTEGER NOT NULL REFERENCES queues(id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES records(id),
    status    TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(queue_id, record_id)
);

CREATE TABLE IF NOT EXISTS annotations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_item_id INTEGER NOT NULL UNIQUE REFERENCES queue_items(id) ON DELETE CASCADE,
    "values"      TEXT NOT NULL,
    updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS datasets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dataset_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id    INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    record_id     TEXT NOT NULL REFERENCES records(id),
    source        TEXT NOT NULL,
    queue_item_id INTEGER REFERENCES queue_items(id),
    UNIQUE(dataset_id, record_id)
);
""")
