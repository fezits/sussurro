import numpy as np

from meeting.audio.vad import Vad


def _speech_like(seconds: float, sr: int = 16000) -> np.ndarray:
    """Synthetic harmonic signal in the voice frequency range with an envelope.
    Empirically produces silero-vad probabilities near 1.0, so the test does
    not depend on real speech audio."""
    t = np.arange(int(seconds * sr)) / sr
    base = (
        np.sin(2 * np.pi * 150 * t)
        + 0.5 * np.sin(2 * np.pi * 300 * t)
        + 0.3 * np.sin(2 * np.pi * 450 * t)
    )
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 5 * t)
    return (base * envelope * 0.3).astype(np.float32)


def test_vad_emits_turn_end_on_silence():
    vad = Vad(silence_ms=400, sample_rate=16000)

    speech = _speech_like(2.0)
    silence = np.zeros(int(0.5 * 16000), dtype=np.float32)

    events: list[str] = []
    for chunk in np.array_split(speech, 20):
        for e in vad.feed(chunk):
            events.append(e)
    for chunk in np.array_split(silence, 5):
        for e in vad.feed(chunk):
            events.append(e)

    assert "turn_end" in events


def test_vad_no_event_for_pure_silence():
    vad = Vad(silence_ms=400, sample_rate=16000)
    silence = np.zeros(16000, dtype=np.float32)
    events = list(vad.feed(silence))
    assert events == []
