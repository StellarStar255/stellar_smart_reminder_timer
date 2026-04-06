"""Task data repository."""

from typing import List, Optional
from datetime import datetime, date

from src.models import Task, TaskStatus
from src.data.database import Database


class TaskRepository:
    """Repository for task data operations."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, task: Task) -> Task:
        """Create a new task."""
        # Auto-assign display_order to end
        cursor = self.db.execute(
            "SELECT COALESCE(MAX(display_order), -1) FROM tasks WHERE status IN (?, ?)",
            (TaskStatus.RUNNING.value, TaskStatus.PAUSED.value)
        )
        task.display_order = cursor.fetchone()[0] + 1

        cursor = self.db.execute(
            """INSERT INTO tasks (name, duration_seconds, category_id, status,
               elapsed_seconds, created_at, started_at, completed_at, notes, display_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.name, task.duration_seconds, task.category_id, task.status.value,
             task.elapsed_seconds, task.created_at.isoformat(),
             task.started_at.isoformat() if task.started_at else None,
             task.completed_at.isoformat() if task.completed_at else None,
             task.notes, task.display_order)
        )
        self.db.commit()
        task.id = cursor.lastrowid
        return task

    def update(self, task: Task) -> Task:
        """Update an existing task."""
        self.db.execute(
            """UPDATE tasks SET name=?, duration_seconds=?, category_id=?, status=?,
               elapsed_seconds=?, started_at=?, completed_at=?, notes=?, display_order=?
               WHERE id=?""",
            (task.name, task.duration_seconds, task.category_id, task.status.value,
             task.elapsed_seconds,
             task.started_at.isoformat() if task.started_at else None,
             task.completed_at.isoformat() if task.completed_at else None,
             task.notes, task.display_order, task.id)
        )
        self.db.commit()
        return task

    def delete(self, task_id: int):
        """Delete a task."""
        self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.db.commit()

    def get_by_id(self, task_id: int) -> Optional[Task]:
        """Get task by ID."""
        cursor = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_task(row)
        return None

    def get_all(self) -> List[Task]:
        """Get all tasks."""
        cursor = self.db.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_active(self) -> List[Task]:
        """Get all active tasks (running or paused), ordered by display_order."""
        cursor = self.db.execute(
            "SELECT * FROM tasks WHERE status IN (?, ?) ORDER BY display_order ASC",
            (TaskStatus.RUNNING.value, TaskStatus.PAUSED.value)
        )
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_by_category(self, category_id: int) -> List[Task]:
        """Get tasks by category."""
        cursor = self.db.execute(
            "SELECT * FROM tasks WHERE category_id=? ORDER BY created_at DESC",
            (category_id,)
        )
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_by_status(self, status: TaskStatus) -> List[Task]:
        """Get tasks by status."""
        cursor = self.db.execute(
            "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC",
            (status.value,)
        )
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_today_completed(self) -> List[Task]:
        """Get tasks completed today."""
        today = date.today().isoformat()
        cursor = self.db.execute(
            """SELECT * FROM tasks
               WHERE status=? AND date(completed_at)=?
               ORDER BY completed_at DESC""",
            (TaskStatus.COMPLETED.value, today)
        )
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_completed_between(self, start_date: date, end_date: date) -> List[Task]:
        """Get tasks completed between two dates."""
        cursor = self.db.execute(
            """SELECT * FROM tasks
               WHERE status=? AND date(completed_at) BETWEEN ? AND ?
               ORDER BY completed_at DESC""",
            (TaskStatus.COMPLETED.value, start_date.isoformat(), end_date.isoformat())
        )
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def record_completion(self, task: Task):
        """Record task completion in history."""
        today = date.today().isoformat()
        self.db.execute(
            """INSERT INTO task_history (task_id, category_id, duration_seconds,
               elapsed_seconds, completed_at, date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task.id, task.category_id, task.duration_seconds,
             task.elapsed_seconds, task.completed_at.isoformat(), today)
        )

        # Update daily stats
        self.db.execute(
            """INSERT INTO daily_stats (date, total_tasks, completed_tasks, total_focus_seconds)
               VALUES (?, 0, 1, ?)
               ON CONFLICT(date) DO UPDATE SET
               completed_tasks = completed_tasks + 1,
               total_focus_seconds = total_focus_seconds + ?""",
            (today, task.elapsed_seconds, task.elapsed_seconds)
        )
        self.db.commit()

    def update_display_orders(self, order_mapping: list):
        """Batch update display_order for multiple tasks.

        Args:
            order_mapping: list of (display_order, task_id) tuples
        """
        self.db.executemany(
            "UPDATE tasks SET display_order = ? WHERE id = ?",
            order_mapping
        )
        self.db.commit()

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task object."""
        return Task(
            id=row['id'],
            name=row['name'],
            duration_seconds=row['duration_seconds'],
            category_id=row['category_id'],
            status=TaskStatus(row['status']),
            elapsed_seconds=row['elapsed_seconds'],
            created_at=datetime.fromisoformat(row['created_at']),
            started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
            notes=row['notes'] or '',
            display_order=row['display_order'] if 'display_order' in row.keys() else 0,
        )
