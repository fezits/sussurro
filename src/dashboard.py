"""Dashboard window: browse past meetings, open transcripts, delete sessions.

Reads from base_dir / 'reunioes/<timestamp>/' folders. Each folder is one
session containing transcript.txt and sumario.md (and optionally audio.wav).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
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


@dataclass
class SessionInfo:
    dir: Path
    name: str
    transcript_size: int
    summary_size: int
    has_audio: bool
    n_turns: int
    when: datetime | None

    @property
    def display(self) -> str:
        when = self.when.strftime("%d/%m/%Y %H:%M") if self.when else self.name
        return f"{when}  ·  {self.n_turns} turnos"


def scan_sessions(reunioes_dir: Path) -> list[SessionInfo]:
    if not reunioes_dir.exists():
        return []
    sessions: list[SessionInfo] = []
    for d in sorted(reunioes_dir.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        transcript = d / "transcript.txt"
        summary = d / "sumario.md"
        audio = d / "audio.wav"
        n_turns = 0
        if transcript.exists():
            try:
                n_turns = sum(1 for line in transcript.read_text(encoding="utf-8").splitlines() if line.strip())
            except Exception:
                n_turns = 0
        try:
            when = datetime.strptime(d.name, "%Y-%m-%d_%H-%M")
        except Exception:
            when = None
        sessions.append(
            SessionInfo(
                dir=d,
                name=d.name,
                transcript_size=transcript.stat().st_size if transcript.exists() else 0,
                summary_size=summary.stat().st_size if summary.exists() else 0,
                has_audio=audio.exists(),
                n_turns=n_turns,
                when=when,
            )
        )
    return sessions


class Dashboard(QWidget):
    """Standalone window: list of past meetings + transcript/summary viewer."""

    def __init__(self, base_dir: Path) -> None:
        super().__init__(None)
        self.base_dir = Path(base_dir)
        self.reunioes_dir = self.base_dir / "reunioes"
        self.setWindowTitle("Sussurro · Reuniões anteriores")
        self.resize(960, 620)
        self.setStyleSheet(
            "QWidget { background-color: #14141A; color: #DDDDE5; }"
            "QListWidget { background-color: #1A1A22; border: none; padding: 4px; }"
            "QListWidget::item { padding: 10px 12px; border-radius: 6px; margin: 2px 0; }"
            "QListWidget::item:selected { background-color: rgba(124, 196, 255, 60); color: white; }"
            "QListWidget::item:hover:!selected { background-color: rgba(255,255,255,12); }"
            "QPushButton { "
            "  background-color: rgba(255,255,255,14); color: #DDDDE5; "
            "  border: 1px solid rgba(255,255,255,28); border-radius: 6px; padding: 6px 12px; }"
            "QPushButton:hover { background-color: rgba(124,196,255,60); }"
            "QTabWidget::pane { border: 1px solid rgba(255,255,255,20); border-radius: 6px; }"
            "QTabBar::tab { padding: 6px 14px; background-color: transparent; color: #9090A0; }"
            "QTabBar::tab:selected { color: #DDDDE5; border-bottom: 2px solid #7CC4FF; }"
            "QTextEdit, QTextBrowser { background-color: #101014; color: #DDDDE5; border: none; padding: 8px; }"
            "QLabel#footer { color: #9090A0; font-size: 11px; padding: 6px 8px; }"
        )

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 0)
        outer.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: list + refresh + footer
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        list_header = QHBoxLayout()
        list_title = QLabel("Reuniões")
        list_title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px 6px;")
        list_header.addWidget(list_title, 1)
        refresh_btn = QPushButton("↻")
        refresh_btn.setToolTip("Recarregar lista")
        refresh_btn.setFixedWidth(32)
        refresh_btn.clicked.connect(self.refresh)
        list_header.addWidget(refresh_btn)
        left_layout.addLayout(list_header)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_selection_change)
        left_layout.addWidget(self.list_widget, 1)

        list_actions = QHBoxLayout()
        self.open_dir_btn = QPushButton("📂 Pasta")
        self.open_dir_btn.clicked.connect(self._open_current_dir)
        list_actions.addWidget(self.open_dir_btn)
        self.export_btn = QPushButton("⬇  Exportar")
        self.export_btn.clicked.connect(self._export_current)
        list_actions.addWidget(self.export_btn)
        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setToolTip("Excluir esta reunião")
        self.delete_btn.setFixedWidth(40)
        self.delete_btn.clicked.connect(self._delete_current)
        list_actions.addWidget(self.delete_btn)
        left_layout.addLayout(list_actions)

        splitter.addWidget(left)

        # Right: tabs
        self.tabs = QTabWidget()
        self.transcript_view = QTextEdit()
        self.transcript_view.setReadOnly(True)
        self.transcript_view.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.transcript_view, "Transcript")

        self.summary_view = QTextBrowser()
        self.summary_view.setOpenExternalLinks(True)
        self.tabs.addTab(self.summary_view, "Sumário")

        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 680])
        outer.addWidget(splitter, 1)

        self.footer = QLabel()
        self.footer.setObjectName("footer")
        outer.addWidget(self.footer)

    def refresh(self) -> None:
        self.list_widget.clear()
        sessions = scan_sessions(self.reunioes_dir)
        self._sessions = sessions
        for s in sessions:
            item = QListWidgetItem(s.display)
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.list_widget.addItem(item)
        if sessions:
            self.list_widget.setCurrentRow(0)
        else:
            self.transcript_view.setPlainText("")
            self.summary_view.setPlainText("")
        self.footer.setText(
            f"{len(sessions)} reunião(ões) em {self.reunioes_dir}"
        )

    def _current(self) -> SessionInfo | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_selection_change(self, *_args) -> None:
        sess = self._current()
        if sess is None:
            return
        transcript = sess.dir / "transcript.txt"
        summary = sess.dir / "sumario.md"
        if transcript.exists():
            try:
                self.transcript_view.setPlainText(transcript.read_text(encoding="utf-8"))
            except Exception as e:
                self.transcript_view.setPlainText(f"[erro ao ler transcript: {e}]")
        else:
            self.transcript_view.setPlainText("(transcript.txt não encontrado)")
        if summary.exists():
            try:
                self.summary_view.setMarkdown(summary.read_text(encoding="utf-8"))
            except Exception as e:
                self.summary_view.setPlainText(f"[erro ao ler sumário: {e}]")
        else:
            self.summary_view.setPlainText("(sumario.md não encontrado)")

    def _open_current_dir(self) -> None:
        sess = self._current()
        if sess is not None:
            _open_path(sess.dir)

    def _export_current(self) -> None:
        sess = self._current()
        if sess is None:
            return
        suggested = f"sussurro_{sess.name}.md"
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar reunião",
            suggested,
            "Markdown (*.md);;Texto (*.txt);;Todos (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        parts: list[str] = []
        parts.append(f"# Reunião {sess.name}\n\n")
        summary = sess.dir / "sumario.md"
        if summary.exists():
            parts.append("## Sumário\n\n")
            parts.append(summary.read_text(encoding="utf-8"))
            parts.append("\n\n---\n\n")
        transcript = sess.dir / "transcript.txt"
        if transcript.exists():
            parts.append("## Transcript\n\n```\n")
            parts.append(transcript.read_text(encoding="utf-8"))
            parts.append("\n```\n")
        try:
            path.write_text("".join(parts), encoding="utf-8")
            QMessageBox.information(self, "Exportado", f"Salvo em:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar:\n{e}")

    def _delete_current(self) -> None:
        sess = self._current()
        if sess is None:
            return
        resp = QMessageBox.question(
            self,
            "Excluir reunião",
            f"Excluir permanentemente a pasta:\n{sess.dir}\n\n"
            f"Isso apaga transcript, sumário e áudio. Sem desfazer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.rmtree(sess.dir)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Falha ao excluir:\n{e}")
            return
        self.refresh()
