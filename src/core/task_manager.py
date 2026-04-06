"""Task lifecycle management."""

from typing import List, Optional, Callable
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from src.models import Task, TaskStatus, Preset
from src.data.database import Database
from src.data.repositories import TaskRepository, CategoryRepository, PresetRepository
from src.core.timer_engine import TimerEngine


class TaskManager(QObject):
    """Manages task lifecycle and coordinates with timer engine."""

    # Signals
    task_created = pyqtSignal(object)  # Task
    task_updated = pyqtSignal(object)  # Task
    task_deleted = pyqtSignal(int)  # task_id
    task_completed = pyqtSignal(object)  # Task

    def __init__(self, db: Database, timer_engine: TimerEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.timer_engine = timer_engine

        self.task_repo = TaskRepository(db)
        self.category_repo = CategoryRepository(db)
        self.preset_repo = PresetRepository(db)

        # Connect timer engine signals
        self.timer_engine.task_completed.connect(self._on_timer_completed)
        self.timer_engine.tick.connect(self._on_timer_tick)

    def create_task(self, name: str, duration_seconds: int, category_id: int,
                    notes: str = "") -> Task:
        """Create a new task."""
        task = Task(
            name=name,
            duration_seconds=duration_seconds,
            category_id=category_id,
            notes=notes,
        )
        task = self.task_repo.create(task)
        self.timer_engine.add_task(task)
        self.task_created.emit(task)
        return task

    def create_from_preset(self, preset: Preset, name: Optional[str] = None) -> Task:
        """Create a task from a preset."""
        task_name = name or preset.name
        task = self.create_task(
            name=task_name,
            duration_seconds=preset.duration_seconds,
            category_id=preset.category_id,
        )
        # Increment preset usage
        self.preset_repo.increment_use_count(preset.id)
        return task

    def start_task(self, task_id: int):
        """Start a task timer."""
        self.timer_engine.start(task_id)
        task = self.timer_engine.get_task(task_id)
        if task:
            self.task_repo.update(task)
            self.task_updated.emit(task)

    def pause_task(self, task_id: int):
        """Pause a task timer."""
        self.timer_engine.pause(task_id)
        task = self.timer_engine.get_task(task_id)
        if task:
            self.task_repo.update(task)
            self.task_updated.emit(task)

    def resume_task(self, task_id: int):
        """Resume a paused task."""
        self.timer_engine.resume(task_id)
        task = self.timer_engine.get_task(task_id)
        if task:
            self.task_repo.update(task)
            self.task_updated.emit(task)

    def stop_task(self, task_id: int):
        """Stop a task timer."""
        self.timer_engine.stop(task_id)
        task = self.timer_engine.get_task(task_id)
        if task:
            self.task_repo.update(task)
            self.task_updated.emit(task)

    def toggle_task(self, task_id: int):
        """Toggle task between running and paused."""
        self.timer_engine.toggle(task_id)
        task = self.timer_engine.get_task(task_id)
        if task:
            self.task_repo.update(task)
            self.task_updated.emit(task)

    def delete_task(self, task_id: int):
        """Delete a task."""
        self.timer_engine.remove_task(task_id)
        self.task_repo.delete(task_id)
        self.task_deleted.emit(task_id)

    def get_task(self, task_id: int) -> Optional[Task]:
        """Get a task by ID."""
        return self.timer_engine.get_task(task_id)

    def get_active_tasks(self) -> List[Task]:
        """Get all active tasks."""
        return self.timer_engine.active_tasks

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks from database."""
        return self.task_repo.get_all()

    def get_tasks_by_category(self, category_id: int) -> List[Task]:
        """Get tasks by category."""
        return self.task_repo.get_by_category(category_id)

    def get_today_completed(self) -> List[Task]:
        """Get tasks completed today."""
        return self.task_repo.get_today_completed()

    def load_active_tasks(self):
        """Load active tasks from database into timer engine.

        All tasks are loaded as paused on restart, since timers were not
        running while the app was closed.
        """
        active_tasks = self.task_repo.get_active()
        for task in active_tasks:
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.PAUSED
                self.task_repo.update(task)
            self.timer_engine.add_task(task)

    def _on_timer_completed(self, task_id: int):
        """Handle timer completion."""
        task = self.timer_engine.get_task(task_id)
        if task:
            self.task_repo.update(task)
            self.task_repo.record_completion(task)
            self.task_completed.emit(task)

    def _on_timer_tick(self, task_id: int):
        """Handle timer tick - periodic save."""
        task = self.timer_engine.get_task(task_id)
        if task and task.elapsed_seconds % 30 == 0:  # Save every 30 seconds
            self.task_repo.update(task)
