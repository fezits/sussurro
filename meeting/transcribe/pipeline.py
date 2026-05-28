from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Queue
from typing import Protocol

import numpy as np

from meeting.transcribe.turn import Speaker, Turn

try:
    from src import logger as _slog
    log = _slog.get("pipeline")
except Exception:
    import logging as _logging
    log = _logging.getLogger("sussurro.pipeline")


class _Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...


class TranscribePipeline:
    """Submits (speaker, audio) jobs and emits Turn objects via on_turn."""

    def __init__(
        self,
        transcriber: _Transcriber,
        on_turn: Callable[[Turn], None],
        workers: int = 2,
        sample_rate: int = 16000,
        meeting_start: datetime | None = None,
    ) -> None:
        self.transcriber = transcriber
        self.on_turn = on_turn
        self.workers = workers
        self.sample_rate = sample_rate
        self.meeting_start = meeting_start or datetime.now()
        self._pool: ThreadPoolExecutor | None = None
        self._queue: Queue = Queue()
        self._running = False
        self._dispatcher: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="transcribe")
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)  # poison pill
        if self._dispatcher:
            self._dispatcher.join(timeout=2)
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=False)
        self._pool = None

    def submit(self, speaker: Speaker, audio: np.ndarray) -> None:
        if not self._running or audio.size == 0:
            return
        wall = datetime.now()
        self._queue.put((speaker, audio, wall))

    def _dispatch_loop(self) -> None:
        while self._running:
            item = self._queue.get()
            if item is None:
                return
            speaker, audio, wall = item
            assert self._pool is not None
            self._pool.submit(self._work, speaker, audio, wall)

    def _work(self, speaker: Speaker, audio: np.ndarray, wall: datetime) -> None:
        seconds = audio.size / self.sample_rate
        log.info("Transcribing · speaker=%s · %.2fs", speaker.value, seconds)
        try:
            text = self.transcriber.transcribe(audio).strip()
        except Exception:
            log.exception("transcriber.transcribe FAILED · speaker=%s · %.2fs", speaker.value, seconds)
            return
        log.info("Transcribed · speaker=%s · text=%r", speaker.value, text[:120])
        if not text:
            log.info("Empty transcription (silence/noise) · speaker=%s · %.2fs", speaker.value, seconds)
            return
        duration = audio.size / self.sample_rate
        end_seconds = (wall - self.meeting_start).total_seconds()
        start_seconds = max(0.0, end_seconds - duration)
        turn = Turn(
            speaker=speaker,
            start=start_seconds,
            end=end_seconds,
            text=text,
            wall_clock=wall,
        )
        try:
            self.on_turn(turn)
        except Exception:
            log.exception("on_turn callback failed")
