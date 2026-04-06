"""Statistics and analytics engine."""

from typing import Dict, List, Tuple
from datetime import date, datetime, timedelta
from dataclasses import dataclass

from src.data.database import Database


@dataclass
class DailyStats:
    """Statistics for a single day."""
    date: date
    total_tasks: int
    completed_tasks: int
    total_focus_seconds: int

    @property
    def total_focus_minutes(self) -> int:
        return self.total_focus_seconds // 60

    @property
    def total_focus_hours(self) -> float:
        return self.total_focus_seconds / 3600

    def format_focus_time(self) -> str:
        """Format focus time as human-readable string."""
        hours = self.total_focus_seconds // 3600
        minutes = (self.total_focus_seconds % 3600) // 60

        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        return f"{minutes}分钟"


@dataclass
class CategoryStats:
    """Statistics for a category."""
    category_id: int
    category_name: str
    category_color: str
    total_tasks: int
    total_seconds: int

    @property
    def percentage(self) -> float:
        return 0.0  # Will be calculated in context


@dataclass
class TaskTimeStats:
    """Time statistics for a specific task name."""
    task_name: str
    total_seconds: int
    task_count: int
    category_color: str

    def format_time(self) -> str:
        """Format total time as human-readable string."""
        hours = self.total_seconds // 3600
        minutes = (self.total_seconds % 3600) // 60
        if hours > 0:
            if minutes > 0:
                return f"{hours}h{minutes}m"
            return f"{hours}h"
        return f"{minutes}m"


class StatisticsEngine:
    """Engine for computing and retrieving statistics."""

    def __init__(self, db: Database):
        self.db = db

    def get_today_stats(self) -> DailyStats:
        """Get statistics for today."""
        today = date.today().isoformat()
        cursor = self.db.execute(
            "SELECT * FROM daily_stats WHERE date = ?",
            (today,)
        )
        row = cursor.fetchone()

        if row:
            return DailyStats(
                date=date.fromisoformat(row['date']),
                total_tasks=row['total_tasks'],
                completed_tasks=row['completed_tasks'],
                total_focus_seconds=row['total_focus_seconds'],
            )

        return DailyStats(
            date=date.today(),
            total_tasks=0,
            completed_tasks=0,
            total_focus_seconds=0,
        )

    def get_stats_range(self, start_date: date, end_date: date) -> List[DailyStats]:
        """Get statistics for a date range."""
        cursor = self.db.execute(
            """SELECT * FROM daily_stats
               WHERE date BETWEEN ? AND ?
               ORDER BY date""",
            (start_date.isoformat(), end_date.isoformat())
        )

        stats = []
        for row in cursor.fetchall():
            stats.append(DailyStats(
                date=date.fromisoformat(row['date']),
                total_tasks=row['total_tasks'],
                completed_tasks=row['completed_tasks'],
                total_focus_seconds=row['total_focus_seconds'],
            ))
        return stats

    def get_week_stats(self) -> List[DailyStats]:
        """Get statistics for the past 7 days."""
        end_date = date.today()
        start_date = end_date - timedelta(days=6)
        return self.get_stats_range(start_date, end_date)

    def get_month_stats(self) -> List[DailyStats]:
        """Get statistics for the past 30 days."""
        end_date = date.today()
        start_date = end_date - timedelta(days=29)
        return self.get_stats_range(start_date, end_date)

    def get_streak(self) -> int:
        """Get current streak (consecutive days with completed tasks)."""
        cursor = self.db.execute(
            """SELECT date FROM daily_stats
               WHERE completed_tasks > 0
               ORDER BY date DESC"""
        )

        streak = 0
        expected_date = date.today()

        for row in cursor.fetchall():
            row_date = date.fromisoformat(row['date'])

            if row_date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif row_date < expected_date:
                break

        return streak

    def get_category_distribution(self, days: int = 7) -> List[CategoryStats]:
        """Get time distribution by category."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        cursor = self.db.execute(
            """SELECT c.id, c.name, c.color,
                      COUNT(h.id) as task_count,
                      COALESCE(SUM(h.elapsed_seconds), 0) as total_seconds
               FROM categories c
               LEFT JOIN task_history h ON c.id = h.category_id
                   AND h.date BETWEEN ? AND ?
               GROUP BY c.id
               ORDER BY total_seconds DESC""",
            (start_date.isoformat(), end_date.isoformat())
        )

        stats = []
        for row in cursor.fetchall():
            stats.append(CategoryStats(
                category_id=row['id'],
                category_name=row['name'],
                category_color=row['color'],
                total_tasks=row['task_count'],
                total_seconds=row['total_seconds'],
            ))
        return stats

    def get_total_focus_time(self, days: int = 7) -> int:
        """Get total focus time in seconds for the past N days."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        cursor = self.db.execute(
            """SELECT COALESCE(SUM(total_focus_seconds), 0) as total
               FROM daily_stats
               WHERE date BETWEEN ? AND ?""",
            (start_date.isoformat(), end_date.isoformat())
        )
        return cursor.fetchone()['total']

    def get_total_completed_tasks(self, days: int = 7) -> int:
        """Get total completed tasks for the past N days."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        cursor = self.db.execute(
            """SELECT COALESCE(SUM(completed_tasks), 0) as total
               FROM daily_stats
               WHERE date BETWEEN ? AND ?""",
            (start_date.isoformat(), end_date.isoformat())
        )
        return cursor.fetchone()['total']

    def get_average_daily_focus(self, days: int = 7) -> float:
        """Get average daily focus time in seconds."""
        total = self.get_total_focus_time(days)
        return total / days

    def get_task_time_distribution(self, limit: int = 10, days: int = 0) -> List[TaskTimeStats]:
        """Get total time spent per task name.

        Args:
            limit: Maximum number of tasks to return.
            days: Number of days to look back. 0 means all time.
        """
        if days > 0:
            start_date = (date.today() - timedelta(days=days - 1)).isoformat()
            cursor = self.db.execute(
                """SELECT t.name, c.color,
                          COUNT(h.id) as task_count,
                          COALESCE(SUM(h.elapsed_seconds), 0) as total_seconds
                   FROM task_history h
                   JOIN tasks t ON h.task_id = t.id
                   LEFT JOIN categories c ON h.category_id = c.id
                   WHERE h.date >= ?
                   GROUP BY t.name
                   ORDER BY total_seconds DESC
                   LIMIT ?""",
                (start_date, limit)
            )
        else:
            cursor = self.db.execute(
                """SELECT t.name, c.color,
                          COUNT(t.id) as task_count,
                          COALESCE(SUM(t.elapsed_seconds), 0) as total_seconds
                   FROM tasks t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.elapsed_seconds > 0
                   GROUP BY t.name
                   ORDER BY total_seconds DESC
                   LIMIT ?""",
                (limit,)
            )

        stats = []
        for row in cursor.fetchall():
            stats.append(TaskTimeStats(
                task_name=row['name'],
                total_seconds=row['total_seconds'],
                task_count=row['task_count'],
                category_color=row['color'] or '#007AFF',
            ))
        return stats

    def get_category_distribution_range(self, start_date: date, end_date: date) -> List[CategoryStats]:
        """Get time distribution by category for a custom date range."""
        cursor = self.db.execute(
            """SELECT c.id, c.name, c.color,
                      COUNT(h.id) as task_count,
                      COALESCE(SUM(h.elapsed_seconds), 0) as total_seconds
               FROM categories c
               LEFT JOIN task_history h ON c.id = h.category_id
                   AND h.date BETWEEN ? AND ?
               GROUP BY c.id
               ORDER BY total_seconds DESC""",
            (start_date.isoformat(), end_date.isoformat())
        )

        stats = []
        for row in cursor.fetchall():
            stats.append(CategoryStats(
                category_id=row['id'],
                category_name=row['name'],
                category_color=row['color'],
                total_tasks=row['task_count'],
                total_seconds=row['total_seconds'],
            ))
        return stats

    def get_task_time_distribution_range(self, start_date: date, end_date: date, limit: int = 10) -> List[TaskTimeStats]:
        """Get total time spent per task name for a custom date range."""
        cursor = self.db.execute(
            """SELECT t.name, c.color,
                      COUNT(h.id) as task_count,
                      COALESCE(SUM(h.elapsed_seconds), 0) as total_seconds
               FROM task_history h
               JOIN tasks t ON h.task_id = t.id
               LEFT JOIN categories c ON h.category_id = c.id
               WHERE h.date BETWEEN ? AND ?
               GROUP BY t.name
               ORDER BY total_seconds DESC
               LIMIT ?""",
            (start_date.isoformat(), end_date.isoformat(), limit)
        )

        stats = []
        for row in cursor.fetchall():
            stats.append(TaskTimeStats(
                task_name=row['name'],
                total_seconds=row['total_seconds'],
                task_count=row['task_count'],
                category_color=row['color'] or '#007AFF',
            ))
        return stats

    def format_seconds(self, seconds: int) -> str:
        """Format seconds as human-readable string."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        return f"{minutes}分钟"
