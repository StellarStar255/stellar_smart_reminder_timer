"""Category data repository."""

from typing import List, Optional

from src.models import Category
from src.data.database import Database


class CategoryRepository:
    """Repository for category data operations."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, category: Category) -> Category:
        """Create a new category."""
        cursor = self.db.execute(
            """INSERT INTO categories (name, color, icon, is_default, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (category.name, category.color, category.icon,
             category.is_default, category.sort_order)
        )
        self.db.commit()
        category.id = cursor.lastrowid
        return category

    def update(self, category: Category) -> Category:
        """Update an existing category."""
        self.db.execute(
            """UPDATE categories SET name=?, color=?, icon=?, sort_order=?
               WHERE id=?""",
            (category.name, category.color, category.icon,
             category.sort_order, category.id)
        )
        self.db.commit()
        return category

    def delete(self, category_id: int):
        """Delete a category (only non-default)."""
        self.db.execute(
            "DELETE FROM categories WHERE id=? AND is_default=0",
            (category_id,)
        )
        self.db.commit()

    def get_by_id(self, category_id: int) -> Optional[Category]:
        """Get category by ID."""
        cursor = self.db.execute(
            "SELECT * FROM categories WHERE id=?",
            (category_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_category(row)
        return None

    def get_all(self) -> List[Category]:
        """Get all categories."""
        cursor = self.db.execute(
            "SELECT * FROM categories ORDER BY sort_order"
        )
        return [self._row_to_category(row) for row in cursor.fetchall()]

    def get_default(self) -> List[Category]:
        """Get default categories."""
        cursor = self.db.execute(
            "SELECT * FROM categories WHERE is_default=1 ORDER BY sort_order"
        )
        return [self._row_to_category(row) for row in cursor.fetchall()]

    def _row_to_category(self, row) -> Category:
        """Convert database row to Category object."""
        return Category(
            id=row['id'],
            name=row['name'],
            color=row['color'],
            icon=row['icon'],
            is_default=bool(row['is_default']),
            sort_order=row['sort_order'],
        )
