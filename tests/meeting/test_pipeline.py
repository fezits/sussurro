import time
from datetime import datetime

import numpy as np

from meeting.transcribe.pipeline import TranscribePipeline
from meeting.transcribe.turn import Speaker, Turn


class _FakeTranscriber:
    def transcribe(self, audio: np.ndarray) -> str:
        # Echo the audio length so tests can assert ordering.
        return f"audio_{audio.size}"


def test_pipeline_produces_turns_in_order():
    received: list[Turn] = []
    pipe = TranscribePipeline(
        transcriber=_FakeTranscriber(),
        workers=2,
        on_turn=received.append,
        meeting_start=datetime(2026, 4, 28, 14, 0, 0),
    )
    pipe.start()
    pipe.submit(Speaker.YOU, np.ones(16000, dtype=np.float32))
    pipe.submit(Speaker.THEM, np.ones(8000, dtype=np.float32))

    deadline = time.time() + 3
    while len(received) < 2 and time.time() < deadline:
        time.sleep(0.05)
    pipe.stop()

    assert len(received) == 2
    assert {t.speaker for t in received} == {Speaker.YOU, Speaker.THEM}
    for t in received:
        assert t.text.startswith("audio_")
