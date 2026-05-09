from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QTextEdit

from meeting.transcribe.turn import Speaker, Turn


_SPEAKER_COLOR = {
    Speaker.YOU: "#7CFFA8",   # green
    Speaker.THEM: "#7CC4FF",  # blue
}


class TranscriptView(QTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("background-color: #101014; color: #DDDDE5; padding: 8px;")
        self.setFont(QFont("Consolas", 10))
        self._auto_scroll = True
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, value: int) -> None:
        bar = self.verticalScrollBar()
        self._auto_scroll = value >= bar.maximum() - 4

    def append_turn(self, turn: Turn) -> None:
        ts = turn.wall_clock.strftime("%H:%M:%S")
        color = _SPEAKER_COLOR[turn.speaker]
        speaker_box = f"[{turn.speaker.value}]".ljust(8)
        html = (
            f'<div style="margin: 0 0 4px 0;">'
            f'<span style="color:#666;">{ts}</span> '
            f'<span style="color:{color}; font-weight: bold;">{speaker_box}</span> '
            f'<span style="color:#DDDDE5;">{self._escape(turn.text)}</span>'
            f"</div>"
        )
        self.append(html)
        if self._auto_scroll:
            self.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
