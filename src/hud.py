"""Compact HUD panel shown when the user left-clicks the orb.

Big buttons for the actions you'd want one click away. Opens next to the
orb, dismisses on focus loss or Esc. Designed to feel like a popover, not
a full window.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _open_path(path: Path | str) -> None:
    p = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception:
        pass


class HudPanel(QWidget):
    """Popover-style control panel."""

    meeting_toggle_requested = Signal()
    transcribe_file_requested = Signal()
    dashboard_requested = Signal()
    quit_requested = Signal()

    def __init__(self, base_dir: Path) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

        self.base_dir = Path(base_dir)
        self._meeting_active = False
        self._build_ui()
        QShortcut(QKeySequence("Esc"), self, activated=self.hide)

    def _build_ui(self) -> None:
        # Outer transparent wrapper, inner rounded card.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        card = QFrame()
        card.setObjectName("hudCard")
        card.setStyleSheet(
            "#hudCard {"
            "  background-color: rgba(20, 20, 26, 245);"
            "  border-radius: 14px;"
            "  border: 1px solid rgba(255, 255, 255, 30);"
            "}"
            "QLabel { color: #DDDDE5; }"
            "QPushButton {"
            "  background-color: rgba(255, 255, 255, 14);"
            "  color: #DDDDE5;"
            "  border: 1px solid rgba(255, 255, 255, 28);"
            "  border-radius: 8px;"
            "  padding: 9px 10px;"
            "  text-align: left;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(124, 196, 255, 60);"
            "  border-color: rgba(124, 196, 255, 140);"
            "}"
            "QPushButton#primary {"
            "  background-color: rgba(220, 50, 60, 200);"
            "  border-color: rgba(255, 100, 110, 220);"
            "  color: white;"
            "  font-weight: bold;"
            "}"
            "QPushButton#primary:hover {"
            "  background-color: rgba(240, 70, 80, 220);"
            "}"
            "QPushButton#danger {"
            "  color: #FFB0B0;"
            "}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Header
        title = QLabel("Sussurro")
        title.setStyleSheet("color: #7CC4FF; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.status_label = QLabel("Carregando…")
        self.status_label.setStyleSheet("color: #9090A0; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.env_label = QLabel("")
        self.env_label.setStyleSheet("color: #9090A0; font-size: 10px;")
        layout.addWidget(self.env_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: rgba(255,255,255,30);")
        layout.addWidget(separator)

        # Primary action
        self.meeting_btn = QPushButton("🎙️  Iniciar reunião")
        self.meeting_btn.setObjectName("primary")
        self.meeting_btn.clicked.connect(self._on_meeting_clicked)
        layout.addWidget(self.meeting_btn)

        # Secondary actions
        file_btn = QPushButton("📁  Transcrever arquivo")
        file_btn.clicked.connect(self._on_transcribe_clicked)
        layout.addWidget(file_btn)

        dashboard_btn = QPushButton("📋  Reuniões anteriores")
        dashboard_btn.clicked.connect(self._on_dashboard_clicked)
        layout.addWidget(dashboard_btn)

        # Quick-access buttons row
        row = QHBoxLayout()
        row.setSpacing(6)
        open_folder_btn = QPushButton("📂  Pasta")
        open_folder_btn.setToolTip("Abrir pasta de reuniões")
        open_folder_btn.clicked.connect(lambda: _open_path(self.base_dir / "reunioes"))
        row.addWidget(open_folder_btn)

        profile_btn = QPushButton("📝  Perfil")
        profile_btn.setToolTip("Editar knowledge/perfil.md")
        profile_btn.clicked.connect(
            lambda: _open_path(self.base_dir / "knowledge" / "perfil.md")
        )
        row.addWidget(profile_btn)

        log_btn = QPushButton("📊  Log")
        log_btn.setToolTip("Abrir sussurro.log")
        log_btn.clicked.connect(lambda: _open_path(self.base_dir / "sussurro.log"))
        row.addWidget(log_btn)
        layout.addLayout(row)

        layout.addStretch(1)

        quit_btn = QPushButton("❌  Sair")
        quit_btn.setObjectName("danger")
        quit_btn.clicked.connect(self._on_quit_clicked)
        layout.addWidget(quit_btn)

        outer.addWidget(card)
        self.setFixedSize(280, 420)

    # ── public API ─────────────────────────────────────────────────────

    def update_status(self, status: str, env_msg: str = "") -> None:
        self.status_label.setText(status)
        if env_msg:
            self.env_label.setText(env_msg)
            self.env_label.show()
        else:
            self.env_label.hide()

    def set_meeting_active(self, active: bool) -> None:
        self._meeting_active = active
        self.meeting_btn.setText("⏹  Parar reunião" if active else "🎙️  Iniciar reunião")

    def show_near(self, anchor_pos: QPoint, anchor_size_w: int, anchor_size_h: int) -> None:
        """Position the HUD just to the left of the orb (or above if no room)."""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        screen_rect = screen.availableGeometry() if screen else None

        margin = 8
        x = anchor_pos.x() - self.width() - margin
        y = anchor_pos.y() + anchor_size_h // 2 - self.height() // 2
        if screen_rect is not None:
            if x < screen_rect.left():
                # Not enough room on left: try above
                x = anchor_pos.x() + anchor_size_w // 2 - self.width() // 2
                y = anchor_pos.y() - self.height() - margin
                if y < screen_rect.top():
                    y = anchor_pos.y() + anchor_size_h + margin
            x = max(screen_rect.left() + margin, min(x, screen_rect.right() - self.width() - margin))
            y = max(screen_rect.top() + margin, min(y, screen_rect.bottom() - self.height() - margin))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    # ── private slots ──────────────────────────────────────────────────

    def _on_meeting_clicked(self) -> None:
        self.hide()
        self.meeting_toggle_requested.emit()

    def _on_transcribe_clicked(self) -> None:
        self.hide()
        self.transcribe_file_requested.emit()

    def _on_dashboard_clicked(self) -> None:
        self.hide()
        self.dashboard_requested.emit()

    def _on_quit_clicked(self) -> None:
        self.hide()
        self.quit_requested.emit()

    def focusOutEvent(self, event) -> None:
        # Dismiss when user clicks outside the panel.
        self.hide()
        super().focusOutEvent(event)
