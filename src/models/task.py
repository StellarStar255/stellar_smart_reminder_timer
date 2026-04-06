"""Task data model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a timer task."""

    name: str
    duration_seconds: int
    category_id: int

    id: Optional[int] = None
    status: TaskStatus = TaskStatus.PENDING
    elapsed_seconds: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: str = ""
    display_order: int = 0

    @property
    def remaining_seconds(self) -> int:
        """Get remaining time in seconds."""
        return max(0, self.duration_seconds - self.elapsed_seconds)

    @property
    def progress(self) -> float:
        """Get progress as a value between 0 and 1."""
        if self.duration_seconds == 0:
            return 1.0
        return min(1.0, self.elapsed_seconds / self.duration_seconds)

    @property
    def is_active(self) -> bool:
        """Check if task is currently active (running or paused)."""
        return self.status in (TaskStatus.RUNNING, TaskStatus.PAUSED)

    @property
    def is_completed(self) -> bool:
        """Check if task is completed."""
        return self.status == TaskStatus.COMPLETED

    def format_remaining(self) -> str:
        """Format remaining time as MM:SS or HH:MM:SS."""
        total = self.remaining_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def format_elapsed(self) -> str:
        """Format elapsed time as MM:SS or HH:MM:SS."""
        total = self.elapsed_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def format_duration(self) -> str:
        """Format total duration as MM:SS or HH:MM:SS."""
        total = self.duration_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict:
        """Convert task to dictionary for database storage."""
        return {
            'id': self.id,
            'name': self.name,
            'duration_seconds': self.duration_seconds,
            'category_id': self.category_id,
            'status': self.status.value,
            'elapsed_seconds': self.elapsed_seconds,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'notes': self.notes,
            'display_order': self.display_order,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """Create task from dictionary."""
        return cls(
            id=data.get('id'),
            name=data['name'],
            duration_seconds=data['duration_seconds'],
            category_id=data['category_id'],
            status=TaskStatus(data.get('status', 'pending')),
            elapsed_seconds=data.get('elapsed_seconds', 0),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else None,
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            notes=data.get('notes', ''),
            display_order=data.get('display_order', 0),
        )
