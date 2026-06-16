"""Decode any audio/video file into 16kHz mono float32 chunks, on demand.

Uses PyAV (already a transitive dep of faster-whisper). Works for mp3, mp4,
wav, m4a, ogg, webm, mkv, etc — anything ffmpeg can demux.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np

try:
    import av  # type: ignore
except ImportError as e:  # pragma: no cover
    raise RuntimeError("PyAV not installed; needed for file transcription") from e


def probe_duration_seconds(path: Path | str) -> float:
    """Best-effort duration of the file in seconds. 0.0 if unknown."""
    container = av.open(str(path))
    try:
        duration_us = container.duration
        if duration_us is None or duration_us <= 0:
            return 0.0
        return float(duration_us) / 1_000_000.0
    finally:
        container.close()


def iter_chunks(
    path: Path | str,
    chunk_seconds: float = 30.0,
    target_rate: int = 16000,
) -> Iterator[np.ndarray]:
    """Yield mono float32 chunks of ~chunk_seconds at target_rate.

    Each yielded chunk is between 1×chunk_seconds and 2×chunk_seconds long
    (we don't split frames mid-decode). Last chunk may be shorter.
    """
    container = av.open(str(path))
    try:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise RuntimeError(f"No audio stream in {path}")

        resampler = av.audio.resampler.AudioResampler(
            format="flt", layout="mono", rate=target_rate
        )

        chunk_samples = int(chunk_seconds * target_rate)
        buffer = np.zeros(0, dtype=np.float32)

        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                arr = resampled.to_ndarray().reshape(-1).astype(np.float32)
                buffer = np.concatenate([buffer, arr])
                if buffer.size >= chunk_samples:
                    yield buffer
                    buffer = np.zeros(0, dtype=np.float32)

        # Flush resampler
        for resampled in resampler.resample(None):
            arr = resampled.to_ndarray().reshape(-1).astype(np.float32)
            buffer = np.concatenate([buffer, arr])

        if buffer.size > 0:
            yield buffer
    finally:
        container.close()
