"""Wall-clock scheduler for date/time reminders.

Unlike TimerEngine — which counts elapsed seconds while the app runs — this
scheduler only ever compares the current wall-clock time against each
reminder's next due time. That keeps reminders correct across app restarts
and system sleep: a reminder due while the Mac was asleep is noticed on the
very next tick after it wakes.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.models import Reminder, RepeatMode, MISSED_GRACE_SECONDS
from src.data.repositories import ReminderRepository


class ReminderScheduler(QObject):
    """Fires reminders at their scheduled date and time."""

    # Signals
    reminder_due = pyqtSignal(object)      # Reminder — ring now
    reminder_missed = pyqtSignal(object)   # Reminder — recorded, no alarm
    reminders_changed = pyqtSignal()       # the list or any state changed

    CHECK_INTERVAL_MS = 1000

    def __init__(self, repo: ReminderRepository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._reminders: Dict[int, Reminder] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self.check_now)

    # --- Lifecycle ---

    def start(self):
        """Load reminders and begin checking the clock."""
        self.reload()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def reload(self):
        """Re-read every reminder from the database."""
        self._reminders = {r.id: r for r in self._repo.get_all() if r.id is not None}
        self.reminders_changed.emit()

    # --- Queries ---

    @property
    def reminders(self) -> List[Reminder]:
        """All reminders, pending ones first (soonest first), then the rest."""
        def sort_key(r: Reminder):
            due = r.next_due()
            # Pending reminders sort ahead of finished/disabled ones, which
            # fall back to their scheduled time so they stay in a stable order.
            return (0, due) if due else (1, r.remind_at)

        return sorted(self._reminders.values(), key=sort_key)

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self._reminders.values() if r.next_due() is not None)

    def next_pending(self) -> Optional[Reminder]:
        """The reminder that will fire soonest, if any."""
        pending = [r for r in self._reminders.values() if r.next_due() is not None]
        if not pending:
            return None
        return min(pending, key=lambda r: r.next_due())

    def get(self, reminder_id: int) -> Optional[Reminder]:
        return self._reminders.get(reminder_id)

    # --- Mutations ---

    def add(self, reminder: Reminder) -> Reminder:
        self._repo.create(reminder)
        self._reminders[reminder.id] = reminder
        self.reminders_changed.emit()
        return reminder

    def update(self, reminder: Reminder) -> Reminder:
        self._repo.update(reminder)
        self._reminders[reminder.id] = reminder
        self.reminders_changed.emit()
        return reminder

    def delete(self, reminder_id: int):
        self._repo.delete(reminder_id)
        self._reminders.pop(reminder_id, None)
        self.reminders_changed.emit()

    def delete_finished(self) -> int:
        """Clear out one-off reminders that already fired."""
        count = self._repo.delete_finished()
        if count:
            self.reload()
        return count

    def set_enabled(self, reminder_id: int, enabled: bool):
        reminder = self._reminders.get(reminder_id)
        if not reminder:
            return
        reminder.enabled = enabled
        if enabled:
            # A stale snooze would fire the moment it is switched back on.
            reminder.snoozed_until = None
            # Switching an already-fired one-off back on re-arms it, but only
            # if its time is still ahead — otherwise it would ring instantly.
            if (reminder.repeat == RepeatMode.NONE
                    and reminder.last_fired_at
                    and reminder.remind_at > datetime.now()):
                reminder.last_fired_at = None
        self.update(reminder)

    def snooze(self, reminder_id: int, minutes: int):
        """Push a reminder out by ``minutes`` without touching its schedule."""
        reminder = self._reminders.get(reminder_id)
        if not reminder:
            return
        reminder.enabled = True
        reminder.snoozed_until = datetime.now() + timedelta(minutes=minutes)
        self.update(reminder)

    # --- The clock check ---

    def check_now(self):
        """Fire every reminder whose due time has arrived."""
        now = datetime.now()
        fired = False

        for reminder in list(self._reminders.values()):
            due = reminder.next_due()
            if due is None or due > now:
                continue

            was_snoozed = reminder.snoozed_until is not None
            # A fire long past its due time means the app was closed or the
            # Mac asleep; record it quietly instead of ringing out of the blue.
            missed = (now - due).total_seconds() > MISSED_GRACE_SECONDS

            reminder.snoozed_until = None
            reminder.last_fired_at = now
            self._repo.update(reminder)
            fired = True

            if missed and not was_snoozed:
                self.reminder_missed.emit(reminder)
            else:
                self.reminder_due.emit(reminder)

        if fired:
            self.reminders_changed.emit()
