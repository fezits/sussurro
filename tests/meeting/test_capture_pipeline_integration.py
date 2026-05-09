import time
from datetime import datetime

import numpy as np

from meeting.audio.channel_buffer import ChannelBuffer
from meeting.audio.vad import Vad
from meeting.transcribe.pipeline import TranscribePipeline
from meeting.transcribe.turn import Speaker, Turn


class _FakeTranscriber:
    def transcribe(self, audio):
        return f"chunk_{audio.size}"


def _speech_like(seconds: float, sr: int = 16000) -> np.ndarray:
    """Synthetic harmonic signal in the voice frequency range with envelope.
    Same fixture as test_vad — produces VAD probabilities ~1.0 reliably."""
    t = np.arange(int(seconds * sr)) / sr
    base = (
        np.sin(2 * np.pi * 150 * t)
        + 0.5 * np.sin(2 * np.pi * 300 * t)
        + 0.3 * np.sin(2 * np.pi * 450 * t)
    )
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 5 * t)
    return (base * envelope * 0.3).astype(np.float32)


def test_full_path_speech_then_silence_creates_one_turn():
    received: list[Turn] = []
    pipe = TranscribePipeline(
        transcriber=_FakeTranscriber(),
        on_turn=received.append,
        workers=1,
        meeting_start=datetime.now(),
    )
    pipe.start()

    vad = Vad(silence_ms=400)
    buf = ChannelBuffer(
        speaker=Speaker.THEM,
        on_chunk=lambda s, a: pipe.submit(s, a),
        max_seconds=60.0,
    )

    speech = _speech_like(2.0)
    silence = np.zeros(int(0.6 * 16000), dtype=np.float32)
    for chunk in np.array_split(speech, 20):
        buf.feed_audio(chunk)
        for ev in vad.feed(chunk):
            if ev == "turn_end":
                buf.on_turn_end()
    for chunk in np.array_split(silence, 5):
        buf.feed_audio(chunk)
        for ev in vad.feed(chunk):
            if ev == "turn_end":
                buf.on_turn_end()

    deadline = time.time() + 3
    while not received and time.time() < deadline:
        time.sleep(0.05)
    pipe.stop()

    assert len(received) == 1
    assert received[0].speaker is Speaker.THEM
    assert received[0].text.startswith("chunk_")
