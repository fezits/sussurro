from __future__ import annotations

from pathlib import Path

import numpy as np

from src.transcriber import Transcriber


class MeetingTranscriber:
    """Lightweight adapter so meeting code uses the same Whisper instance config
    as dictation/server. Currently just strips trailing whitespace."""

    def __init__(
        self,
        model_size: str = "small",
        language: str | None = "pt",
        download_root: Path | str | None = "models",
        beam_size: int = 1,
        vad_filter: bool = False,  # we already chunked by VAD upstream
    ) -> None:
        self._inner = Transcriber(
            model_size=model_size,
            language=language,
            download_root=download_root,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )

    def transcribe(self, audio: np.ndarray) -> str:
        return self._inner.transcribe(audio).strip()

    @property
    def device(self) -> str:
        return self._inner.device
