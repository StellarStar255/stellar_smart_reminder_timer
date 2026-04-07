"""Preset data model."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Preset:
    """Represents a timer preset (quick start template)."""

    name: str
    duration_seconds: int
    category_id: int

    id: Optional[int] = None
    is_default: bool = False
    sort_order: int = 0
    use_count: int = 0  # Track usage for smart recommendations
    last_used_at: Optional[str] = None  # ISO timestamp of last usage
    star_rating: int = 0  # Importance rating, 0-5 stars

    @property
    def duration_minutes(self) -> int:
        """Get duration in minutes."""
        return self.duration_seconds // 60

    def format_duration(self) -> str:
        """Format duration as human-readable string."""
        minutes = self.duration_seconds // 60
        if minutes >= 60:
            hours = minutes // 60
            mins = minutes % 60
            if mins > 0:
                return f"{hours}小时{mins}分钟"
            return f"{hours}小时"
        return f"{minutes}分钟"

    def to_dict(self) -> dict:
        """Convert preset to dictionary for database storage."""
        return {
            'id': self.id,
            'name': self.name,
            'duration_seconds': self.duration_seconds,
            'category_id': self.category_id,
            'is_default': self.is_default,
            'sort_order': self.sort_order,
            'use_count': self.use_count,
            'last_used_at': self.last_used_at,
            'star_rating': self.star_rating,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Preset':
        """Create preset from dictionary."""
        return cls(
            id=data.get('id'),
            name=data['name'],
            duration_seconds=data['duration_seconds'],
            category_id=data['category_id'],
            is_default=data.get('is_default', False),
            sort_order=data.get('sort_order', 0),
            use_count=data.get('use_count', 0),
            last_used_at=data.get('last_used_at'),
            star_rating=data.get('star_rating', 0),
        )


# Default presets (Pomodoro-style)
DEFAULT_PRESETS = [
    Preset(name="番茄钟", duration_seconds=25 * 60, category_id=1, is_default=True, sort_order=0),
    Preset(name="短休息", duration_seconds=5 * 60, category_id=3, is_default=True, sort_order=1),
    Preset(name="长休息", duration_seconds=15 * 60, category_id=3, is_default=True, sort_order=2),
    Preset(name="深度工作", duration_seconds=45 * 60, category_id=1, is_default=True, sort_order=3),
    Preset(name="阅读时间", duration_seconds=30 * 60, category_id=2, is_default=True, sort_order=4),
    Preset(name="快速任务", duration_seconds=10 * 60, category_id=1, is_default=True, sort_order=5),
]
