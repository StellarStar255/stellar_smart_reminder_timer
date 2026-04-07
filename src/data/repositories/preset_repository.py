"""Preset data repository."""

from typing import List, Optional
from datetime import datetime

from src.models import Preset
from src.data.database import Database


class PresetRepository:
    """Repository for preset data operations."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, preset: Preset) -> Preset:
        """Create a new preset."""
        cursor = self.db.execute(
            """INSERT INTO presets (name, duration_seconds, category_id,
               is_default, sort_order, use_count, star_rating)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (preset.name, preset.duration_seconds, preset.category_id,
             preset.is_default, preset.sort_order, preset.use_count, preset.star_rating)
        )
        self.db.commit()
        preset.id = cursor.lastrowid
        return preset

    def update(self, preset: Preset) -> Preset:
        """Update an existing preset."""
        self.db.execute(
            """UPDATE presets SET name=?, duration_seconds=?, category_id=?,
               sort_order=?, use_count=?, star_rating=?
               WHERE id=?""",
            (preset.name, preset.duration_seconds, preset.category_id,
             preset.sort_order, preset.use_count, preset.star_rating, preset.id)
        )
        self.db.commit()
        return preset

    def delete(self, preset_id: int):
        """Delete a preset (only non-default)."""
        self.db.execute(
            "DELETE FROM presets WHERE id=? AND is_default=0",
            (preset_id,)
        )
        self.db.commit()

    def get_by_id(self, preset_id: int) -> Optional[Preset]:
        """Get preset by ID."""
        cursor = self.db.execute(
            "SELECT * FROM presets WHERE id=?",
            (preset_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_preset(row)
        return None

    def _sort_by_combined_score(self, presets: List[Preset]) -> List[Preset]:
        """Sort presets by combined score: 10% usage count + 90% recency."""
        if not presets:
            return presets
        max_count = max(p.use_count for p in presets) or 1
        now = datetime.now()
        # Recency: hours since last use, capped at 7 days
        max_hours = 7 * 24
        def combined_score(p):
            count_score = p.use_count / max_count
            if p.last_used_at:
                try:
                    last = datetime.fromisoformat(p.last_used_at)
                    hours_ago = (now - last).total_seconds() / 3600
                    recency_score = max(0, 1 - hours_ago / max_hours)
                except (ValueError, TypeError):
                    recency_score = 0
            else:
                recency_score = 0
            return 0.1 * count_score + 0.9 * recency_score
        return sorted(presets, key=lambda p: (-combined_score(p), p.sort_order))

    def get_all(self) -> List[Preset]:
        """Get all presets, sorted by combined usage count + recency."""
        cursor = self.db.execute("SELECT * FROM presets")
        presets = [self._row_to_preset(row) for row in cursor.fetchall()]
        return self._sort_by_combined_score(presets)

    def get_by_category(self, category_id: int) -> List[Preset]:
        """Get presets by category, sorted by combined usage count + recency."""
        cursor = self.db.execute(
            "SELECT * FROM presets WHERE category_id=?",
            (category_id,)
        )
        presets = [self._row_to_preset(row) for row in cursor.fetchall()]
        return self._sort_by_combined_score(presets)

    def get_most_used(self, limit: int = 5) -> List[Preset]:
        """Get most frequently used presets (combined score)."""
        cursor = self.db.execute("SELECT * FROM presets")
        presets = [self._row_to_preset(row) for row in cursor.fetchall()]
        return self._sort_by_combined_score(presets)[:limit]

    def increment_use_count(self, preset_id: int):
        """Increment usage count and update last_used_at timestamp."""
        now = datetime.now().isoformat()
        self.db.execute(
            "UPDATE presets SET use_count = use_count + 1, last_used_at = ? WHERE id=?",
            (now, preset_id)
        )
        self.db.commit()

    def find_by_name(self, name: str) -> Optional[Preset]:
        """Find the most-used preset by name."""
        cursor = self.db.execute(
            "SELECT * FROM presets WHERE name=? ORDER BY use_count DESC LIMIT 1",
            (name,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_preset(row)
        return None

    def find_by_name_and_duration(self, name: str, duration_seconds: int) -> Optional[Preset]:
        """Find a preset by name and duration (for dedup)."""
        cursor = self.db.execute(
            "SELECT * FROM presets WHERE name=? AND duration_seconds=?",
            (name, duration_seconds)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_preset(row)
        return None

    def _row_to_preset(self, row) -> Preset:
        """Convert database row to Preset object."""
        return Preset(
            id=row['id'],
            name=row['name'],
            duration_seconds=row['duration_seconds'],
            category_id=row['category_id'],
            is_default=bool(row['is_default']),
            sort_order=row['sort_order'],
            use_count=row['use_count'],
            last_used_at=row['last_used_at'],
            star_rating=(row['star_rating'] if 'star_rating' in row.keys() else 0) or 0,
        )
