from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from meeting.intelligence.types import Suggestion
from meeting.transcribe.turn import Turn
from meeting.ui.invisibility import set_window_invisible_to_capture
from meeting.ui.suggestion_card import SuggestionCard
from meeting.ui.transcript_view import TranscriptView


STATE_FILE = Path("meeting/.window_state.json")


class LiveWindow(QWidget):
    pause_requested = Signal()
    stop_requested = Signal()
    force_suggest_requested = Signal()

    def __init__(self, opacity: float = 0.92) -> None:
        flags = Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setWindowOpacity(opacity)
        self.setWindowTitle("Sussurro Meeting")
        self.setMinimumSize(540, 360)
        self.setStyleSheet("background-color: #14141A; color: #DDDDE5;")

        self._invisible = True
        self._build_ui()
        self._restore_geometry()

        # Apply invisibility after first show so winId() is valid.
        QTimer.singleShot(0, self._apply_invisibility)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Sussurro Meeting")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(title)

        self._invis_label = QLabel("🛡️ Invisível")
        self._invis_label.setStyleSheet("color: #7CFFA8;")
        header.addWidget(self._invis_label)

        header.addStretch(1)

        pause_btn = QPushButton("⏸ Pausar")
        pause_btn.clicked.connect(self.pause_requested.emit)
        header.addWidget(pause_btn)
        stop_btn = QPushButton("⏹ Parar")
        stop_btn.clicked.connect(self.stop_requested.emit)
        header.addWidget(stop_btn)
        outer.addLayout(header)

        self._suggestions_holder = QVBoxLayout()
        outer.addLayout(self._suggestions_holder)

        self.transcript = TranscriptView()
        outer.addWidget(self.transcript, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        force_btn = QPushButton("🔁 Forçar sugestão")
        force_btn.clicked.connect(self.force_suggest_requested.emit)
        bottom.addWidget(force_btn)
        outer.addLayout(bottom)

        QShortcut(QKeySequence("Esc"), self, activated=self._dismiss_current)
        QShortcut(QKeySequence("Return"), self, activated=self._use_current)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.pause_requested.emit)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.stop_requested.emit)

        self._current_card: SuggestionCard | None = None
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._dismiss_current)

    def append_turn(self, turn: Turn) -> None:
        self.transcript.append_turn(turn)

    def show_suggestion(self, suggestion: Suggestion, ttl_seconds: int) -> None:
        self._dismiss_current()
        card = SuggestionCard(suggestion)
        card.use_clicked.connect(self._copy_to_clipboard)
        card.dismiss_clicked.connect(self._dismiss_current)
        self._suggestions_holder.addWidget(card)
        self._current_card = card
        self._dismiss_timer.start(ttl_seconds * 1000)

    def _copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self._dismiss_current()

    def _dismiss_current(self) -> None:
        if self._current_card is None:
            return
        self._current_card.deleteLater()
        self._current_card = None
        self._dismiss_timer.stop()

    def _use_current(self) -> None:
        if self._current_card is not None:
            self._copy_to_clipboard(self._current_card.suggestion.text)

    def _apply_invisibility(self) -> None:
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        ok = set_window_invisible_to_capture(hwnd=hwnd, enabled=self._invisible)
        self._invis_label.setText("🛡️ Invisível" if ok and self._invisible else "👁️ Visível")
        self._invis_label.setStyleSheet(
            "color: #7CFFA8;" if ok and self._invisible else "color: #FFB05E;"
        )

    def _restore_geometry(self) -> None:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.setGeometry(data["x"], data["y"], data["w"], data["h"])
        except Exception:
            self.resize(720, 480)

    def closeEvent(self, event) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            geom = self.geometry()
            STATE_FILE.write_text(
                json.dumps({"x": geom.x(), "y": geom.y(), "w": geom.width(), "h": geom.height()}),
                encoding="utf-8",
            )
        except Exception:
            pass
        super().closeEvent(event)
