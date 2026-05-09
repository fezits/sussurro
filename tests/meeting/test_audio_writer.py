import wave
from pathlib import Path

import numpy as np

from meeting.persistence.audio_writer import AudioWriter


def test_audio_writer_emits_valid_wav(tmp_path: Path):
    wpath = tmp_path / "audio.wav"
    aw = AudioWriter(path=wpath, sample_rate=16000)
    aw.start()
    aw.append(np.ones(16000, dtype=np.float32) * 0.5)
    aw.append(np.zeros(8000, dtype=np.float32))
    aw.close()

    with wave.open(str(wpath), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getnframes() == 24000
