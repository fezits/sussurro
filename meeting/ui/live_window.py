from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
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
    closed = Signal()

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
        self._status_label: QLabel | None = None
        self._final_panel: QFrame | None = None

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

    def show_finalization_status(self, message: str) -> None:
        """Show a status bar at the top while stop() is running (transcribing
        remaining turns, summarizing, saving). Replaces any current suggestion
        card with a non-dismissable progress label.
        """
        self._dismiss_current()
        if self._final_panel is not None:
            try:
                self._final_panel.deleteLater()
            except Exception:
                pass
            self._final_panel = None
        if self._status_label is None:
            self._status_label = QLabel(message)
            self._status_label.setStyleSheet(
                "QLabel { background-color: rgba(80,120,200,230); color: white; "
                "padding: 10px 14px; border-radius: 10px; font-weight: bold; }"
            )
            self._suggestions_holder.addWidget(self._status_label)
        else:
            self._status_label.setText(message)

    def show_finalization_complete(self, session_dir: Path, files: dict[str, Path]) -> None:
        """Replace the live UI with a 'meeting saved' panel showing the
        generated files. Buttons: open folder, open transcript, close window.
        """
        if self._status_label is not None:
            try: self._status_label.deleteLater()
            except Exception: pass
            self._status_label = None

        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: rgba(40, 120, 70, 230); border-radius: 10px; } "
            "QLabel { color: white; } "
            "QPushButton { background-color: rgba(255,255,255,30); color: white; "
            "padding: 6px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,80); }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("✅  Reunião salva")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        layout.addWidget(title)

        path_label = QLabel(f"<small>{session_dir}</small>")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setStyleSheet("color: #C8E6C9;")
        layout.addWidget(path_label)

        for name, path in files.items():
            row = QHBoxLayout()
            label = QLabel(f"  • <b>{name}</b>")
            label.setStyleSheet("color: white;")
            row.addWidget(label, 1)
            if path.exists():
                size_kb = path.stat().st_size / 1024
                size_lbl = QLabel(f"<small>{size_kb:,.1f} KB</small>")
                size_lbl.setStyleSheet("color: #C8E6C9;")
                row.addWidget(size_lbl)
            else:
                missing = QLabel("<small>(não gerado)</small>")
                missing.setStyleSheet("color: #FFCDD2;")
                row.addWidget(missing)
            layout.addLayout(row)

        buttons = QHBoxLayout()
        open_folder_btn = QPushButton("📂 Abrir pasta")
        open_folder_btn.clicked.connect(lambda: self._open_path(session_dir))
        buttons.addWidget(open_folder_btn)

        transcript_path = files.get("transcript.txt")
        if transcript_path and transcript_path.exists():
            open_t_btn = QPushButton("📄 Abrir transcript")
            open_t_btn.clicked.connect(lambda: self._open_path(transcript_path))
            buttons.addWidget(open_t_btn)

        summary_path = files.get("sumario.md")
        if summary_path and summary_path.exists():
            open_s_btn = QPushButton("📝 Abrir sumário")
            open_s_btn.clicked.connect(lambda: self._open_path(summary_path))
            buttons.addWidget(open_s_btn)

        buttons.addStretch(1)
        close_btn = QPushButton("✕ Fechar")
        close_btn.clicked.connect(self.close)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._final_panel = panel
        self._suggestions_holder.addWidget(panel)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

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
        # Tell the app the user closed the window so it can clear references
        # without trying to call close() again.
        try:
            self.closed.emit()
        except Exception:
            pass
        super().closeEvent(event)
