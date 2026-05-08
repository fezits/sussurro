import threading
import time

import numpy as np

from meeting.audio.system_capture import SystemCapture


class _FakePyAudio:
    """Mimics pyaudiowpatch enough for SystemCapture."""

    paFloat32 = 1
    paContinue = 0

    def __init__(self) -> None:
        self.opened: list[dict] = []

    def get_default_wasapi_loopback(self):
        return {
            "index": 1,
            "name": "Speakers (Loopback)",
            "defaultSampleRate": 48000,
            "maxInputChannels": 2,
        }

    def open(self, **kwargs):
        self.opened.append(kwargs)
        return _FakeStream(kwargs)

    def terminate(self):
        pass


class _FakeStream:
    def __init__(self, kwargs):
        self.callback = kwargs["stream_callback"]
        self.frames = kwargs.get("frames_per_buffer", 1024)
        self.rate = kwargs.get("rate", 48000)
        self.channels = kwargs.get("channels", 2)
        self._running = False
        self._t: threading.Thread | None = None

    def start_stream(self):
        self._running = True
        def _loop():
            while self._running:
                samples = (np.random.randn(self.frames, self.channels) * 0.05).astype(np.float32)
                self.callback(samples.tobytes(), self.frames, None, 0)
                time.sleep(self.frames / self.rate)
        self._t = threading.Thread(target=_loop, daemon=True)
        self._t.start()

    def stop_stream(self):
        self._running = False
        if self._t: self._t.join(timeout=1)

    def close(self):
        self.stop_stream()


def test_system_capture_resamples_and_downmixes(monkeypatch):
    import meeting.audio.system_capture as mod
    monkeypatch.setattr(mod, "_PyAudio", _FakePyAudio)

    received: list[np.ndarray] = []
    cap = SystemCapture(target_rate=16000, on_audio=lambda c: received.append(c))
    cap.open()
    time.sleep(0.3)
    cap.close()

    assert len(received) > 0
    for c in received:
        assert c.ndim == 1
        assert c.dtype == np.float32
