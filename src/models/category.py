"""Category data model."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Category:
    """Represents a task category."""

    name: str
    color: str  # Hex color code
    icon: str  # Icon name or emoji

    id: Optional[int] = None
    is_default: bool = False
    sort_order: int = 0

    def to_dict(self) -> dict:
        """Convert category to dictionary for database storage."""
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'icon': self.icon,
            'is_default': self.is_default,
            'sort_order': self.sort_order,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Category':
        """Create category from dictionary."""
        return cls(
            id=data.get('id'),
            name=data['name'],
            color=data['color'],
            icon=data['icon'],
            is_default=data.get('is_default', False),
            sort_order=data.get('sort_order', 0),
        )


# Default categories
DEFAULT_CATEGORIES = [
    Category(name="工作", color="#FF6B6B", icon="💼", is_default=True, sort_order=0),
    Category(name="学习", color="#4ECDC4", icon="📚", is_default=True, sort_order=1),
    Category(name="休息", color="#45B7D1", icon="☕", is_default=True, sort_order=2),
    Category(name="运动", color="#96CEB4", icon="🏃", is_default=True, sort_order=3),
    Category(name="其他", color="#9B9B9B", icon="📌", is_default=True, sort_order=4),
]
