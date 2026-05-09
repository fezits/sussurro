import numpy as np

from meeting.transcribe.adapter import MeetingTranscriber


class _StubInner:
    def transcribe(self, audio):
        return "  hello  "


def test_adapter_strips_and_returns_text(monkeypatch):
    adapter = MeetingTranscriber.__new__(MeetingTranscriber)
    adapter._inner = _StubInner()  # type: ignore[attr-defined]
    out = adapter.transcribe(np.zeros(16000, dtype=np.float32))
    assert out == "hello"
