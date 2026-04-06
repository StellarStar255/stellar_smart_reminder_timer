"""Preset management."""

from typing import List, Optional
from datetime import datetime

from src.models import Preset
from src.data.database import Database
from src.data.repositories import PresetRepository


class PresetManager:
    """Manages timer presets with smart recommendations."""

    def __init__(self, db: Database):
        self.db = db
        self.preset_repo = PresetRepository(db)

    def get_all(self) -> List[Preset]:
        """Get all presets."""
        return self.preset_repo.get_all()

    def get_by_id(self, preset_id: int) -> Optional[Preset]:
        """Get preset by ID."""
        return self.preset_repo.get_by_id(preset_id)

    def get_by_category(self, category_id: int) -> List[Preset]:
        """Get presets by category."""
        return self.preset_repo.get_by_category(category_id)

    def create(self, name: str, duration_seconds: int, category_id: int) -> Preset:
        """Create a new custom preset."""
        preset = Preset(
            name=name,
            duration_seconds=duration_seconds,
            category_id=category_id,
            is_default=False,
        )
        return self.preset_repo.create(preset)

    def update(self, preset: Preset) -> Preset:
        """Update a preset."""
        return self.preset_repo.update(preset)

    def delete(self, preset_id: int):
        """Delete a custom preset."""
        self.preset_repo.delete(preset_id)

    def get_recommended(self, limit: int = 4) -> List[Preset]:
        """Get recommended presets based on time of day, usage count and recency."""
        now = datetime.now()
        hour = now.hour
        all_presets = self.preset_repo.get_all()  # already sorted by combined score

        # Time-based recommendations
        if 6 <= hour < 12:  # Morning - work/study focused
            preferred_categories = [1, 2]  # 工作, 学习
        elif 12 <= hour < 14:  # Lunch - rest
            preferred_categories = [3]  # 休息
        elif 14 <= hour < 18:  # Afternoon - work focused
            preferred_categories = [1, 2]  # 工作, 学习
        elif 18 <= hour < 21:  # Evening - mixed
            preferred_categories = [2, 4, 3]  # 学习, 运动, 休息
        else:  # Night - rest
            preferred_categories = [3]  # 休息

        # Sort by: preferred category first, then keep combined score order
        def sort_key(p):
            category_score = 0 if p.category_id in preferred_categories else 100
            return category_score

        sorted_presets = sorted(all_presets, key=sort_key)
        return sorted_presets[:limit]

    def get_most_used(self, limit: int = 5) -> List[Preset]:
        """Get most frequently used presets."""
        return self.preset_repo.get_most_used(limit)

    def record_usage(self, preset_id: int):
        """Record preset usage."""
        self.preset_repo.increment_use_count(preset_id)
