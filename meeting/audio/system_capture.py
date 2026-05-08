from __future__ import annotations

from collections.abc import Callable

import numpy as np

try:
    import pyaudiowpatch as _PyAudioModule
    _PyAudio = _PyAudioModule.PyAudio
except ImportError:  # tests inject a fake
    _PyAudio = None  # type: ignore


class SystemCapture:
    """Captures everything coming out of the speakers via WASAPI loopback.

    Resamples to `target_rate` mono float32 in the audio callback so consumers
    see the same shape MicCapture provides.
    """

    def __init__(
        self,
        target_rate: int = 16000,
        on_audio: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        if _PyAudio is None:
            raise RuntimeError("pyaudiowpatch not available")
        self.target_rate = target_rate
        self.on_audio = on_audio or (lambda _c: None)
        self._pa = _PyAudio()
        self._stream = None
        self._device_rate = 48000
        self._device_channels = 2

    def _callback(self, in_data, frame_count, time_info, status):
        raw = np.frombuffer(in_data, dtype=np.float32)
        if self._device_channels == 2 and raw.size >= 2:
            raw = raw.reshape(-1, 2).mean(axis=1)
        if self._device_rate != self.target_rate and raw.size > 0:
            ratio = self.target_rate / self._device_rate
            new_len = max(1, int(round(raw.size * ratio)))
            x_old = np.linspace(0.0, 1.0, num=raw.size, endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
            raw = np.interp(x_new, x_old, raw).astype(np.float32)
        self.on_audio(np.ascontiguousarray(raw, dtype=np.float32))
        return (None, 0)  # paContinue

    def open(self) -> None:
        if self._stream is not None:
            return
        info = self._pa.get_default_wasapi_loopback()
        self._device_rate = int(info["defaultSampleRate"])
        self._device_channels = int(info.get("maxInputChannels", 2)) or 2
        self._stream = self._pa.open(
            format=getattr(self._pa, "paFloat32", 1),
            channels=self._device_channels,
            rate=self._device_rate,
            input=True,
            input_device_index=info["index"],
            frames_per_buffer=1024,
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            finally:
                self._stream = None
        try:
            self._pa.terminate()
        except Exception:
            pass
