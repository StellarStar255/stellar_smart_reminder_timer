"""Circular progress indicator widget."""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics, QBrush


class CircularProgress(QWidget):
    """A circular progress indicator with time display."""

    # Signal emitted when clicked
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._progress = 0.0  # 0.0 to 1.0
        self._time_text = "00:00"
        self._status_text = ""
        self._hovered = False

        # Colors
        self._track_color = QColor("#e5e5ea")
        self._progress_color = QColor("#007AFF")
        self._text_color = QColor("#1d1d1f")
        self._status_color = QColor("#6e6e73")

        # Dimensions
        self._line_width = 8
        self._min_size = 120

        self.setMinimumSize(self._min_size, self._min_size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setProgress(self, value: float):
        """Set progress value (0.0 to 1.0)."""
        self._progress = max(0.0, min(1.0, value))
        self.update()

    def setTimeText(self, text: str):
        """Set the time display text."""
        self._time_text = text
        self.update()

    def setStatusText(self, text: str):
        """Set the status text below time."""
        self._status_text = text
        self.update()

    def setProgressColor(self, color: str):
        """Set the progress arc color."""
        self._progress_color = QColor(color)
        self.update()

    def setTrackColor(self, color: str):
        """Set the track (background) color."""
        self._track_color = QColor(color)
        self.update()

    def setTextColor(self, color: str):
        """Set the text color."""
        self._text_color = QColor(color)
        self.update()

    def setStatusColor(self, color: str):
        """Set the status text color."""
        self._status_color = QColor(color)
        self.update()

    def setLineWidth(self, width: int):
        """Set the progress line width."""
        self._line_width = width
        self.update()

    def paintEvent(self, event):
        """Paint the circular progress indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate dimensions
        size = min(self.width(), self.height())
        margin = self._line_width / 2 + 2
        rect = QRectF(
            (self.width() - size) / 2 + margin,
            (self.height() - size) / 2 + margin,
            size - margin * 2,
            size - margin * 2
        )

        # Draw hover highlight effect (lighter track when hovered)
        if self._hovered:
            # Draw a subtle fill inside the circle
            fill_color = QColor(self._progress_color)
            fill_color.setAlpha(15)
            painter.setBrush(QBrush(fill_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect)

        # Draw track (background circle)
        track_color = self._track_color
        if self._hovered:
            # Slightly darker track on hover
            track_color = QColor(self._track_color)
            track_color = track_color.darker(105)
        pen = QPen(track_color, self._line_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Draw progress arc
        if self._progress > 0:
            progress_color = self._progress_color
            if self._hovered:
                progress_color = QColor(self._progress_color).lighter(110)
            pen.setColor(progress_color)
            painter.setPen(pen)
            # Start from top (90 degrees) and go clockwise
            start_angle = 90 * 16
            span_angle = -int(self._progress * 360 * 16)
            painter.drawArc(rect, start_angle, span_angle)

        # Draw time text
        time_font = QFont(".AppleSystemUIFont", 24, QFont.Weight.Medium)
        painter.setFont(time_font)
        painter.setPen(self._text_color)

        fm = QFontMetrics(time_font)
        time_rect = fm.boundingRect(self._time_text)
        time_x = (self.width() - time_rect.width()) / 2
        time_y = self.height() / 2 + fm.ascent() / 3

        painter.drawText(int(time_x), int(time_y), self._time_text)

        # Draw status text
        if self._status_text:
            status_font = QFont(".AppleSystemUIFont", 11)
            painter.setFont(status_font)
            painter.setPen(self._status_color)

            fm = QFontMetrics(status_font)
            status_rect = fm.boundingRect(self._status_text)
            status_x = (self.width() - status_rect.width()) / 2
            status_y = time_y + fm.height() + 4

            painter.drawText(int(status_x), int(status_y), self._status_text)

    def sizeHint(self):
        """Return the recommended size."""
        from PyQt6.QtCore import QSize
        return QSize(self._min_size, self._min_size)

    def enterEvent(self, event):
        """Handle mouse enter."""
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leave."""
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
