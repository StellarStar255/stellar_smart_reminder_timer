"""Scheduled reminder data model (wall-clock alarms, not countdowns)."""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Optional


class RepeatMode(Enum):
    """How often a reminder repeats."""
    NONE = "none"
    DAILY = "daily"
    WEEKDAYS = "weekdays"   # Mon-Fri
    WEEKLY = "weekly"
    MONTHLY = "monthly"


REPEAT_LABELS = {
    RepeatMode.NONE: "不重复",
    RepeatMode.DAILY: "每天",
    RepeatMode.WEEKDAYS: "工作日",
    RepeatMode.WEEKLY: "每周",
    RepeatMode.MONTHLY: "每月",
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# A fire this far past its scheduled time counts as "missed" (the app was
# closed or asleep) and is recorded silently instead of ringing.
MISSED_GRACE_SECONDS = 600


def _add_months(d: date, months: int) -> date:
    """Shift a date by whole months, clamping to the target month's length."""
    index = d.month - 1 + months
    year = d.year + index // 12
    month = index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass
class Reminder:
    """A reminder that fires at a wall-clock date and time.

    ``remind_at`` is the anchor: the first scheduled occurrence. It is never
    rewritten as the reminder fires, so every later occurrence of a repeating
    reminder is derived from the original date — a "每月 31 日" reminder falls
    back to the 30th in short months without permanently drifting there.
    """

    title: str
    remind_at: datetime

    id: Optional[int] = None
    repeat: RepeatMode = RepeatMode.NONE
    enabled: bool = True
    notes: str = ""
    # >0: also start a timer of this many minutes when the reminder fires.
    auto_start_minutes: int = 0
    category_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_fired_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None

    # --- Scheduling ---

    def next_due(self) -> Optional[datetime]:
        """When this reminder should fire next, or None if nothing is pending."""
        if not self.enabled:
            return None
        if self.snoozed_until:
            return self.snoozed_until
        if self.repeat == RepeatMode.NONE:
            return None if self.last_fired_at else self.remind_at
        # Repeating: the first occurrence strictly after the last fire; a
        # microsecond back from the anchor makes the anchor itself eligible.
        after = self.last_fired_at or (self.remind_at - timedelta(microseconds=1))
        return self._first_occurrence_after(after)

    def arm(self, now: Optional[datetime] = None) -> 'Reminder':
        """Skip occurrences that are already in the past.

        Scheduling "每天 08:00" at three in the afternoon anchors the reminder
        on a time that has been and gone; without this it would be treated as
        an occurrence the app slept through and reported as 已错过 the moment
        it was saved. One-off reminders can't hit this — the editor refuses a
        past time for them.
        """
        now = now or datetime.now()
        if self.repeat != RepeatMode.NONE and self.remind_at <= now:
            self.last_fired_at = now
        return self

    def _first_occurrence_after(self, after: datetime) -> Optional[datetime]:
        """First repeat occurrence strictly later than ``after``.

        Occurrences are built by stepping whole days/months on the anchor date
        and re-attaching the anchor's time of day, so a DST change shifts the
        UTC instant rather than the wall-clock time the user picked.
        """
        anchor_date = self.remind_at.date()
        at: time = self.remind_at.time()

        if self.repeat in (RepeatMode.DAILY, RepeatMode.WEEKLY):
            step = 1 if self.repeat == RepeatMode.DAILY else 7
            k = max(0, (after.date() - anchor_date).days // step)
            while True:
                candidate = datetime.combine(anchor_date + timedelta(days=k * step), at)
                if candidate > after:
                    return candidate
                k += 1

        if self.repeat == RepeatMode.WEEKDAYS:
            day = max(anchor_date, after.date())
            while True:
                candidate = datetime.combine(day, at)
                if day.weekday() < 5 and candidate > after:
                    return candidate
                day += timedelta(days=1)

        if self.repeat == RepeatMode.MONTHLY:
            k = max(0, (after.year - anchor_date.year) * 12
                    + (after.month - anchor_date.month))
            while True:
                candidate = datetime.combine(_add_months(anchor_date, k), at)
                if candidate > after:
                    return candidate
                k += 1

        return None

    @property
    def is_finished(self) -> bool:
        """A one-off reminder that has already fired."""
        return (self.repeat == RepeatMode.NONE
                and self.last_fired_at is not None
                and self.snoozed_until is None)

    @property
    def was_missed(self) -> bool:
        """Fired so late that it was recorded silently instead of ringing."""
        if not self.is_finished or self.last_fired_at is None:
            return False
        return (self.last_fired_at - self.remind_at).total_seconds() > MISSED_GRACE_SECONDS

    # --- Display helpers ---

    def describe_repeat(self) -> str:
        """Human-readable repeat rule, e.g. 每周（周三）."""
        if self.repeat == RepeatMode.WEEKLY:
            return f"每周{WEEKDAY_NAMES[self.remind_at.weekday()][1:]}"
        if self.repeat == RepeatMode.MONTHLY:
            return f"每月{self.remind_at.day}日"
        return REPEAT_LABELS.get(self.repeat, "不重复")

    @staticmethod
    def format_datetime(dt: datetime, now: Optional[datetime] = None) -> str:
        """Format an absolute time relative to today (今天/明天/日期)."""
        now = now or datetime.now()
        delta_days = (dt.date() - now.date()).days
        clock = dt.strftime("%H:%M")
        if delta_days == 0:
            return f"今天 {clock}"
        if delta_days == 1:
            return f"明天 {clock}"
        if delta_days == 2:
            return f"后天 {clock}"
        if 0 < delta_days < 7:
            return f"{WEEKDAY_NAMES[dt.weekday()]} {clock}"
        if dt.year == now.year:
            return dt.strftime(f"%m月%d日 {clock}")
        return dt.strftime(f"%Y年%m月%d日 {clock}")

    @staticmethod
    def format_countdown(target: datetime, now: Optional[datetime] = None) -> str:
        """Format the wait until ``target`` as 还有 X 天 Y 小时 Z 分。"""
        now = now or datetime.now()
        total = int((target - now).total_seconds())
        if total <= 0:
            return "即将提醒"
        days, rest = divmod(total, 86400)
        hours, rest = divmod(rest, 3600)
        minutes, seconds = divmod(rest, 60)
        if days:
            return f"还有 {days} 天 {hours} 小时"
        if hours:
            return f"还有 {hours} 小时 {minutes} 分"
        if minutes:
            return f"还有 {minutes} 分 {seconds} 秒"
        return f"还有 {seconds} 秒"

    def status_text(self, now: Optional[datetime] = None) -> str:
        """One-line state for the reminder list."""
        now = now or datetime.now()
        if not self.enabled:
            return "已关闭"
        if self.snoozed_until:
            return f"已推迟 · {self.format_countdown(self.snoozed_until, now)}"
        due = self.next_due()
        if due is None:
            return "已错过" if self.was_missed else "已完成"
        return self.format_countdown(due, now)

    # --- Serialization ---

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'remind_at': self.remind_at.isoformat(),
            'repeat_mode': self.repeat.value,
            'enabled': 1 if self.enabled else 0,
            'notes': self.notes,
            'auto_start_minutes': self.auto_start_minutes,
            'category_id': self.category_id,
            'created_at': self.created_at.isoformat(),
            'last_fired_at': self.last_fired_at.isoformat() if self.last_fired_at else None,
            'snoozed_until': self.snoozed_until.isoformat() if self.snoozed_until else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Reminder':
        def parse(value):
            return datetime.fromisoformat(value) if value else None

        try:
            repeat = RepeatMode(data.get('repeat_mode') or 'none')
        except ValueError:
            repeat = RepeatMode.NONE

        return cls(
            id=data.get('id'),
            title=data['title'],
            remind_at=parse(data['remind_at']) or datetime.now(),
            repeat=repeat,
            enabled=bool(data.get('enabled', 1)),
            notes=data.get('notes', '') or '',
            auto_start_minutes=data.get('auto_start_minutes', 0) or 0,
            category_id=data.get('category_id'),
            created_at=parse(data.get('created_at')) or datetime.now(),
            last_fired_at=parse(data.get('last_fired_at')),
            snoozed_until=parse(data.get('snoozed_until')),
        )
