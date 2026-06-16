from __future__ import annotations

import math
from enum import Enum
from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget


class OverlayState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    LOADING = "loading"
    ERROR = "error"


STATE_COLORS = {
    OverlayState.IDLE: (QColor(80, 80, 90), QColor(140, 140, 155)),
    OverlayState.RECORDING: (QColor(220, 50, 60), QColor(255, 90, 100)),
    OverlayState.TRANSCRIBING: (QColor(230, 170, 30), QColor(255, 210, 80)),
    OverlayState.LOADING: (QColor(80, 120, 200), QColor(120, 170, 255)),
    OverlayState.ERROR: (QColor(150, 30, 30), QColor(200, 60, 60)),
}


class OrbOverlay(QWidget):
    quit_requested = Signal()
    meeting_toggle_requested = Signal()
    transcribe_file_requested = Signal()

    LABEL_H = 26
    LABEL_MARGIN = 6

    def __init__(
        self,
        size: int = 72,
        level_provider: Callable[[], float] | None = None,
    ) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)

        self._orb_size = size
        self._label_width = max(size + 80, 200)
        self._level_provider = level_provider or (lambda: 0.0)

        total_w = self._label_width
        total_h = size + self.LABEL_MARGIN + self.LABEL_H
        self.setFixedSize(total_w, total_h)
        self.setToolTip("Sussurro — segure Ctrl+Win para falar")

        self._state = OverlayState.LOADING
        self._status_text = "Carregando…"
        self._progress: float | None = None
        self._phase = 0.0
        self._drag_offset: QPoint | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._place_default_corner()

    def _place_default_corner(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        margin = 24
        x = geo.right() - self.width() - margin
        y = geo.bottom() - self.height() - margin
        self.move(x, y)

    def set_state(self, state: OverlayState, status: str | None = None, progress: float | None = None) -> None:
        self._state = state
        if status is not None:
            self._status_text = status
            self.setToolTip(f"Sussurro — {status}")
        self._progress = progress

    def _tick(self) -> None:
        self._phase += 0.08
        if self._phase > math.tau:
            self._phase -= math.tau
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        orb_h = self._orb_size
        cx, cy = w / 2, orb_h / 2
        base_r = self._orb_size / 2 - 6

        pulse = 0.0
        level = 0.0
        if self._state == OverlayState.RECORDING:
            level = max(0.0, min(1.0, self._level_provider() * 6.0))
            pulse = 0.12 * (0.5 + 0.5 * math.sin(self._phase * 2))
        elif self._state == OverlayState.TRANSCRIBING:
            pulse = 0.08 * (0.5 + 0.5 * math.sin(self._phase * 3))
        elif self._state == OverlayState.LOADING:
            pulse = 0.06 * (0.5 + 0.5 * math.sin(self._phase * 2))

        r = base_r * (1 + pulse * 0.5 + level * 0.08)

        dark, light = STATE_COLORS[self._state]
        glow = QRadialGradient(cx, cy, r * 1.6)
        glow.setColorAt(0.0, QColor(light.red(), light.green(), light.blue(), 90))
        glow.setColorAt(0.7, QColor(light.red(), light.green(), light.blue(), 30))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QRectF(cx - r * 1.6, cy - r * 1.6, r * 3.2, r * 3.2))

        body = QRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 1.4)
        body.setColorAt(0.0, light)
        body.setColorAt(1.0, dark)
        p.setBrush(QBrush(body))
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        if self._state == OverlayState.RECORDING:
            self._draw_waveform(p, cx, cy, r, level)
        elif self._state == OverlayState.TRANSCRIBING:
            self._draw_spinner(p, cx, cy, r)
        elif self._state == OverlayState.LOADING:
            self._draw_spinner(p, cx, cy, r)
        else:
            self._draw_mic(p, cx, cy, r)

        self._draw_label(p, w, orb_h)

    def _draw_label(self, p: QPainter, total_w: int, orb_h: int) -> None:
        from PySide6.QtGui import QFont, QFontMetrics

        label_y = orb_h + self.LABEL_MARGIN
        label_h = self.LABEL_H
        label_rect = QRectF(6, label_y, total_w - 12, label_h)

        bg = QColor(20, 20, 24, 210)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        path = QPainterPath()
        path.addRoundedRect(label_rect, label_h / 2, label_h / 2)
        p.drawPath(path)

        if self._progress is not None:
            prog = max(0.0, min(1.0, self._progress))
            fill_w = (label_rect.width() - 4) * prog
            fill_rect = QRectF(label_rect.x() + 2, label_rect.y() + 2, max(0.0, fill_w), label_rect.height() - 4)
            dark, light = STATE_COLORS[self._state]
            grad = QLinearGradient(fill_rect.x(), 0, fill_rect.x() + fill_rect.width(), 0)
            grad.setColorAt(0.0, QColor(dark.red(), dark.green(), dark.blue(), 200))
            grad.setColorAt(1.0, QColor(light.red(), light.green(), light.blue(), 230))
            p.setBrush(QBrush(grad))
            fpath = QPainterPath()
            inner_r = max(0.0, (label_h - 4) / 2)
            fpath.addRoundedRect(fill_rect, inner_r, inner_r)
            p.drawPath(fpath)

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QPen(QColor(245, 245, 250, 240)))

        text = self._status_text
        if self._progress is not None:
            text = f"{text}  {int(self._progress * 100)}%"

        metrics = QFontMetrics(font)
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(label_rect.width()) - 16)
        p.drawText(label_rect, int(Qt.AlignmentFlag.AlignCenter), elided)

    def _draw_waveform(self, p: QPainter, cx: float, cy: float, r: float, level: float) -> None:
        bars = 7
        spacing = r * 0.22
        max_h = r * 1.2
        min_h = r * 0.18
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 230)))
        for i in range(bars):
            phase = self._phase * 3 + i * 0.9
            osc = 0.5 + 0.5 * math.sin(phase)
            target = min_h + (max_h - min_h) * (0.3 + 0.7 * level) * osc
            x = cx + (i - (bars - 1) / 2) * spacing
            rect = QRectF(x - spacing * 0.3, cy - target / 2, spacing * 0.6, target)
            path = QPainterPath()
            path.addRoundedRect(rect, spacing * 0.3, spacing * 0.3)
            p.drawPath(path)

    def _draw_spinner(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        p.save()
        p.translate(cx, cy)
        arc_r = r * 0.55
        pen = QPen(QColor(255, 255, 255, 230), max(2.0, r * 0.12))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        start = int((-self._phase * 180 / math.pi) * 16) % (360 * 16)
        span = 270 * 16
        p.drawArc(QRectF(-arc_r, -arc_r, arc_r * 2, arc_r * 2), start, span)
        p.restore()

    def _draw_mic(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 220)))
        body_w = r * 0.6
        body_h = r * 0.9
        rect = QRectF(cx - body_w / 2, cy - body_h / 2 - r * 0.1, body_w, body_h)
        path = QPainterPath()
        path.addRoundedRect(rect, body_w / 2, body_w / 2)
        p.drawPath(path)

        pen = QPen(QColor(255, 255, 255, 220), max(2.0, r * 0.08))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc_r = r * 0.7
        p.drawArc(
            QRectF(cx - arc_r, cy - arc_r * 0.3, arc_r * 2, arc_r * 1.1),
            -160 * 16,
            -220 * 16,
        )
        p.drawLine(int(cx), int(cy + arc_r * 0.8), int(cx), int(cy + arc_r * 1.05))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        status = QAction(f"Status: {self._status_text}", self)
        status.setEnabled(False)
        menu.addAction(status)
        menu.addSeparator()
        meeting_label = "Parar reunião" if getattr(self, "_meeting_active", False) else "Iniciar reunião"
        self.start_meeting_action = QAction(meeting_label, self)
        self.start_meeting_action.triggered.connect(self.meeting_toggle_requested.emit)
        menu.addAction(self.start_meeting_action)

        transcribe_file_action = QAction("Transcrever arquivo…", self)
        transcribe_file_action.setEnabled(not getattr(self, "_meeting_active", False))
        transcribe_file_action.triggered.connect(self.transcribe_file_requested.emit)
        menu.addAction(transcribe_file_action)

        menu.addSeparator()
        quit_action = QAction("Sair", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def set_meeting_active(self, active: bool) -> None:
        if hasattr(self, "start_meeting_action"):
            self.start_meeting_action.setText("Parar reunião" if active else "Iniciar reunião")
        self._meeting_active = active

    @property
    def meeting_active(self) -> bool:
        return getattr(self, "_meeting_active", False)
