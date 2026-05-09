from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from meeting.intelligence.types import Suggestion, SuggestionKind


_KIND_VISUAL = {
    SuggestionKind.PERSONAL:  ("🧠 Pessoal",  QColor(120, 100, 30)),
    SuggestionKind.TECHNICAL: ("📚 Técnica",  QColor(40, 80, 140)),
    SuggestionKind.HYBRID:    ("🔀 Híbrida",  QColor(110, 60, 150)),
}


class SuggestionCard(QFrame):
    use_clicked = Signal(str)
    dismiss_clicked = Signal()

    def __init__(self, suggestion: Suggestion, parent=None) -> None:
        super().__init__(parent)
        self.suggestion = suggestion
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        label_text, color = _KIND_VISUAL[suggestion.kind]
        self.setStyleSheet(
            f"QFrame {{ background-color: rgba({color.red()},{color.green()},{color.blue()},230);"
            f"  border-radius: 10px; }} QLabel {{ color: white; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(f"💡 SUGESTÃO  {label_text}")
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title, 1)

        use_btn = QPushButton("✓ Usar")
        use_btn.clicked.connect(lambda: self.use_clicked.emit(suggestion.text))
        header.addWidget(use_btn)

        dismiss_btn = QPushButton("✕")
        dismiss_btn.clicked.connect(self.dismiss_clicked.emit)
        header.addWidget(dismiss_btn)

        layout.addLayout(header)

        body = QLabel(suggestion.text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)
