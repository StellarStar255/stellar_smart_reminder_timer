"""SQLite database management."""

import sqlite3
from pathlib import Path
from typing import Optional
import threading


class Database:
    """SQLite database manager with connection pooling."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Store in user's application support directory
            app_dir = Path.home() / ".stellarpulse"
            app_dir.mkdir(exist_ok=True)
            db_path = str(app_dir / "data.db")

        self.db_path = db_path
        self._local = threading.local()

    @property
    def connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA foreign_keys = ON")
        return self._local.connection

    def initialize(self):
        """Initialize database schema."""
        self._create_tables()
        self._migrate_schema()
        self._seed_default_data()

    def _create_tables(self):
        """Create database tables."""
        cursor = self.connection.cursor()

        # Categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT NOT NULL,
                icon TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0
            )
        """)

        # Presets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                is_default INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                use_count INTEGER DEFAULT 0,
                star_rating INTEGER DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)

        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                elapsed_seconds INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                notes TEXT DEFAULT '',
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)

        # Task history table for statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                elapsed_seconds INTEGER NOT NULL,
                completed_at TEXT NOT NULL,
                date TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)

        # Daily statistics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                total_focus_seconds INTEGER DEFAULT 0
            )
        """)

        # App settings key-value store
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY NOT NULL,
                value TEXT NOT NULL
            )
        """)

        # Task notebooks (per-task-name notes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_notebooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT UNIQUE NOT NULL,
                content TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            )
        """)

        self.connection.commit()

    def _migrate_schema(self):
        """Add columns that may not exist in older databases."""
        try:
            self.connection.execute("ALTER TABLE tasks ADD COLUMN display_order INTEGER DEFAULT 0")
            self.connection.commit()
        except Exception:
            pass  # Column already exists

        try:
            self.connection.execute("ALTER TABLE presets ADD COLUMN last_used_at TEXT")
            self.connection.commit()
        except Exception:
            pass  # Column already exists

        try:
            self.connection.execute("ALTER TABLE presets ADD COLUMN star_rating INTEGER DEFAULT 0")
            self.connection.commit()
        except Exception:
            pass  # Column already exists

        self._backfill_stopped_task_history()

    def _backfill_stopped_task_history(self):
        """Backfill history for manually-stopped tasks.

        Stops recorded before task_history captured them left their focus
        time invisible in every date-ranged stat. Insert those tasks into
        task_history once; NOT EXISTS keeps this idempotent across restarts.
        """
        from datetime import date
        cursor = self.connection.execute(
            """SELECT id, category_id, duration_seconds, elapsed_seconds,
                      COALESCE(completed_at, started_at, created_at) AS ended_at
               FROM tasks t
               WHERE status = 'cancelled' AND elapsed_seconds > 0
                 AND NOT EXISTS (SELECT 1 FROM task_history h WHERE h.task_id = t.id)"""
        )
        rows = cursor.fetchall()
        if not rows:
            return
        for row in rows:
            day = (row['ended_at'] or '')[:10] or date.today().isoformat()
            self.connection.execute(
                """INSERT INTO task_history (task_id, category_id, duration_seconds,
                   elapsed_seconds, completed_at, date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (row['id'], row['category_id'], row['duration_seconds'],
                 row['elapsed_seconds'], row['ended_at'], day)
            )
            self.connection.execute(
                """INSERT INTO daily_stats (date, total_tasks, completed_tasks, total_focus_seconds)
                   VALUES (?, 0, 0, ?)
                   ON CONFLICT(date) DO UPDATE SET
                   total_focus_seconds = total_focus_seconds + ?""",
                (day, row['elapsed_seconds'], row['elapsed_seconds'])
            )
        self.connection.commit()

    def _seed_default_data(self):
        """Seed default categories and presets if empty."""
        cursor = self.connection.cursor()

        # Check if categories exist
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            from src.models import DEFAULT_CATEGORIES
            for cat in DEFAULT_CATEGORIES:
                cursor.execute(
                    """INSERT INTO categories (name, color, icon, is_default, sort_order)
                       VALUES (?, ?, ?, ?, ?)""",
                    (cat.name, cat.color, cat.icon, cat.is_default, cat.sort_order)
                )

        # Check if presets exist
        cursor.execute("SELECT COUNT(*) FROM presets")
        if cursor.fetchone()[0] == 0:
            from src.models import DEFAULT_PRESETS
            for preset in DEFAULT_PRESETS:
                cursor.execute(
                    """INSERT INTO presets (name, duration_seconds, category_id, is_default, sort_order, use_count)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (preset.name, preset.duration_seconds, preset.category_id,
                     preset.is_default, preset.sort_order, preset.use_count)
                )

        self.connection.commit()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        return self.connection.cursor().execute(query, params)

    def executemany(self, query: str, params_list: list) -> sqlite3.Cursor:
        """Execute a query with multiple parameter sets."""
        return self.connection.cursor().executemany(query, params_list)

    def commit(self):
        """Commit current transaction."""
        self.connection.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        """Get a setting value by key."""
        row = self.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        """Set a setting value (insert or update)."""
        self.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.commit()

    def get_notebook(self, task_name: str) -> str:
        """Get notebook content for a task name."""
        row = self.execute(
            "SELECT content FROM task_notebooks WHERE task_name = ?", (task_name,)
        ).fetchone()
        return row[0] if row else ""

    def save_notebook(self, task_name: str, content: str):
        """Save notebook content for a task name (upsert)."""
        from datetime import datetime
        now = datetime.now().isoformat()
        self.execute(
            "INSERT OR REPLACE INTO task_notebooks (task_name, content, updated_at) VALUES (?, ?, ?)",
            (task_name, content, now)
        )
        self.commit()

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
