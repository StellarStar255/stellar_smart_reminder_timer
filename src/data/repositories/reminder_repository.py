"""Scheduled reminder repository."""

from typing import List, Optional

from src.models import Reminder
from src.data.database import Database


class ReminderRepository:
    """Repository for reminder data operations."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, reminder: Reminder) -> Reminder:
        """Insert a new reminder and populate its id."""
        data = reminder.to_dict()
        cursor = self.db.execute(
            """INSERT INTO reminders (title, remind_at, repeat_mode, enabled, notes,
               auto_start_minutes, category_id, created_at, last_fired_at, snoozed_until)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data['title'], data['remind_at'], data['repeat_mode'], data['enabled'],
             data['notes'], data['auto_start_minutes'], data['category_id'],
             data['created_at'], data['last_fired_at'], data['snoozed_until'])
        )
        self.db.commit()
        reminder.id = cursor.lastrowid
        return reminder

    def update(self, reminder: Reminder) -> Reminder:
        """Persist changes to an existing reminder."""
        data = reminder.to_dict()
        self.db.execute(
            """UPDATE reminders SET title=?, remind_at=?, repeat_mode=?, enabled=?,
               notes=?, auto_start_minutes=?, category_id=?, last_fired_at=?,
               snoozed_until=? WHERE id=?""",
            (data['title'], data['remind_at'], data['repeat_mode'], data['enabled'],
             data['notes'], data['auto_start_minutes'], data['category_id'],
             data['last_fired_at'], data['snoozed_until'], reminder.id)
        )
        self.db.commit()
        return reminder

    def delete(self, reminder_id: int):
        """Delete a reminder."""
        self.db.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
        self.db.commit()

    def get_by_id(self, reminder_id: int) -> Optional[Reminder]:
        row = self.db.execute(
            "SELECT * FROM reminders WHERE id=?", (reminder_id,)
        ).fetchone()
        return Reminder.from_dict(dict(row)) if row else None

    def get_all(self) -> List[Reminder]:
        """All reminders, earliest scheduled time first."""
        rows = self.db.execute(
            "SELECT * FROM reminders ORDER BY remind_at ASC"
        ).fetchall()
        return [Reminder.from_dict(dict(row)) for row in rows]

    def delete_finished(self) -> int:
        """Delete one-off reminders that already fired. Returns the count."""
        cursor = self.db.execute(
            "DELETE FROM reminders WHERE repeat_mode='none' AND last_fired_at IS NOT NULL"
            " AND snoozed_until IS NULL"
        )
        self.db.commit()
        return cursor.rowcount
