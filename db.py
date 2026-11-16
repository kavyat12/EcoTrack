import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


if os.environ.get("ECOTRACK_DATA_DIR"):
    DATA_DIR = Path(os.environ["ECOTRACK_DATA_DIR"]).expanduser()
elif os.environ.get("LOCALAPPDATA"):
    DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "EcoTrack"
else:
    DATA_DIR = Path.home() / ".local" / "share" / "EcoTrack"
DB_PATH = DATA_DIR / "ecotrack.db"


@contextmanager
def connect_database():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect_database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                title TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                urgency TEXT NOT NULL CHECK (urgency IN ('low', 'medium', 'high')),
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'scheduled', 'resolved')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY,
                report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
                area TEXT NOT NULL,
                scheduled_date TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled', 'in_progress', 'completed')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS waste_entries (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                weight_kg REAL NOT NULL CHECK (weight_kg > 0),
                recycled_kg REAL NOT NULL DEFAULT 0
                    CHECK (recycled_kg >= 0 AND recycled_kg <= weight_kg),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS carbon_activities (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                activity_type TEXT NOT NULL,
                quantity REAL NOT NULL CHECK (quantity > 0),
                unit TEXT NOT NULL,
                emissions_kg REAL NOT NULL CHECK (emissions_kg >= 0),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
        for table in ("reports", "collections"):
            columns = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if "user_id" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
                )
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS reports_user_idx ON reports(user_id, created_at);
            CREATE INDEX IF NOT EXISTS collections_user_idx
                ON collections(user_id, scheduled_date);
            CREATE INDEX IF NOT EXISTS waste_user_idx ON waste_entries(user_id, created_at);
            CREATE INDEX IF NOT EXISTS carbon_user_idx
                ON carbon_activities(user_id, created_at);
            """
        )
        connection.executemany(
            "INSERT OR IGNORE INTO categories (name, color) VALUES (?, ?)",
            [
                ("Recyclables", "#39a875"),
                ("Organic", "#d59749"),
                ("Hazardous", "#d46d5e"),
                ("General waste", "#75809a"),
                ("Electronic", "#7183de"),
            ],
        )
