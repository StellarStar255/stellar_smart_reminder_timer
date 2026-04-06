"""Multi-task timer engine."""

from typing import Dict, Callable, Optional
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.models import Task, TaskStatus


class TimerEngine(QObject):
    """Engine for managing multiple concurrent timers."""

    # Signals
    tick = pyqtSignal(int)  # task_id
    task_completed = pyqtSignal(int)  # task_id
    task_started = pyqtSignal(int)  # task_id
    task_paused = pyqtSignal(int)  # task_id
    task_resumed = pyqtSignal(int)  # task_id
    task_stopped = pyqtSignal(int)  # task_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: Dict[int, Task] = {}
        self._timers: Dict[int, QTimer] = {}

    @property
    def running_count(self) -> int:
        """Get number of currently running timers."""
        return sum(1 for task in self._tasks.values()
                   if task.status == TaskStatus.RUNNING)

    @property
    def active_tasks(self) -> list:
        """Get list of active tasks."""
        return [task for task in self._tasks.values() if task.is_active]

    def add_task(self, task: Task) -> int:
        """Add a task to the engine."""
        if task.id is None:
            raise ValueError("Task must have an ID")
        self._tasks[task.id] = task
        return task.id

    def get_task(self, task_id: int) -> Optional[Task]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def remove_task(self, task_id: int):
        """Remove a task from the engine."""
        self.stop(task_id)
        self._tasks.pop(task_id, None)

    def start(self, task_id: int):
        """Start a timer for a task."""
        task = self._tasks.get(task_id)
        if not task:
            return

        if task.status == TaskStatus.RUNNING:
            return  # Already running

        # Create timer if doesn't exist
        if task_id not in self._timers:
            timer = QTimer(self)
            timer.setInterval(1000)  # 1 second
            timer.timeout.connect(lambda: self._on_tick(task_id))
            self._timers[task_id] = timer

        # Update task state
        task.status = TaskStatus.RUNNING
        if task.started_at is None:
            task.started_at = datetime.now()

        # Start timer
        self._timers[task_id].start()
        self.task_started.emit(task_id)

    def pause(self, task_id: int):
        """Pause a timer."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return

        if task_id in self._timers:
            self._timers[task_id].stop()

        task.status = TaskStatus.PAUSED
        self.task_paused.emit(task_id)

    def resume(self, task_id: int):
        """Resume a paused timer."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.PAUSED:
            return

        task.status = TaskStatus.RUNNING
        if task_id in self._timers:
            self._timers[task_id].start()

        self.task_resumed.emit(task_id)

    def stop(self, task_id: int):
        """Stop a timer."""
        task = self._tasks.get(task_id)
        if not task:
            return

        if task_id in self._timers:
            self._timers[task_id].stop()
            self._timers[task_id].deleteLater()
            del self._timers[task_id]

        if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
            task.status = TaskStatus.CANCELLED
            self.task_stopped.emit(task_id)

    def toggle(self, task_id: int):
        """Toggle timer between running and paused."""
        task = self._tasks.get(task_id)
        if not task:
            return

        if task.status == TaskStatus.RUNNING:
            self.pause(task_id)
        elif task.status in (TaskStatus.PAUSED, TaskStatus.PENDING):
            self.start(task_id)

    def _on_tick(self, task_id: int):
        """Handle timer tick."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return

        task.elapsed_seconds += 1
        self.tick.emit(task_id)

        # Check if completed
        if task.elapsed_seconds >= task.duration_seconds:
            self._complete_task(task_id)

    def _complete_task(self, task_id: int):
        """Mark task as completed."""
        task = self._tasks.get(task_id)
        if not task:
            return

        if task_id in self._timers:
            self._timers[task_id].stop()

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        self.task_completed.emit(task_id)

    def update_task(self, task: Task):
        """Update task in engine."""
        if task.id in self._tasks:
            self._tasks[task.id] = task

    def stop_all(self):
        """Stop all running timers."""
        for task_id in list(self._timers.keys()):
            self.stop(task_id)

    def get_total_running_seconds(self) -> int:
        """Get total elapsed seconds of all running tasks."""
        return sum(
            task.elapsed_seconds
            for task in self._tasks.values()
            if task.status == TaskStatus.RUNNING
        )
