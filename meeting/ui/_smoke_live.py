from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from meeting.intelligence.types import Suggestion, SuggestionKind
from meeting.transcribe.turn import Speaker, Turn
from meeting.ui.live_window import LiveWindow


def main() -> None:
    app = QApplication(sys.argv)
    win = LiveWindow()
    win.show()

    win.append_turn(Turn(Speaker.THEM, 0, 1, "Olá pessoal", datetime.now()))
    win.append_turn(Turn(Speaker.YOU, 1, 2, "Bom dia", datetime.now()))

    QTimer.singleShot(
        500,
        lambda: win.show_suggestion(
            Suggestion(kind=SuggestionKind.HYBRID, text="resposta sugerida.", source_turn_id="x"),
            ttl_seconds=15,
        ),
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
