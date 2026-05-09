from __future__ import annotations

import threading
from pathlib import Path
from queue import Queue, Empty

from meeting.state import SessionId
from meeting.transcribe.turn import Turn


class SessionWriter:
    """Writes transcript.txt incrementally and produces the final sumario.md.

    Runs a daemon thread that drains a queue of Turn objects, appending one line
    each. flush_now() blocks until the queue is empty (used by tests and by
    explicit autosave triggers). finalize() stops the thread and writes the
    summary.
    """

    def __init__(self, root: Path | str, session_id: SessionId) -> None:
        self.root = Path(root)
        self.session_id = session_id
        self.dir = self.root / session_id.value
        self._queue: Queue[Turn | None] = Queue()
        self._thread: threading.Thread | None = None
        self._idle_event = threading.Event()
        self._idle_event.set()

    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        # Truncate transcript at start so re-runs of same session_id are clean.
        (self.dir / "transcript.txt").write_text("", encoding="utf-8")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def append_turn(self, turn: Turn) -> None:
        self._idle_event.clear()
        self._queue.put(turn)

    def flush_now(self, timeout: float = 5.0) -> None:
        self._idle_event.wait(timeout)

    def finalize(self, summary: str) -> None:
        self.flush_now()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
        (self.dir / "sumario.md").write_text(summary, encoding="utf-8")

    def _loop(self) -> None:
        path = self.dir / "transcript.txt"
        while True:
            try:
                turn = self._queue.get(timeout=0.5)
            except Empty:
                self._idle_event.set()
                continue
            if turn is None:
                self._idle_event.set()
                return
            with path.open("a", encoding="utf-8") as f:
                f.write(turn.to_line() + "\n")
            if self._queue.empty():
                self._idle_event.set()
