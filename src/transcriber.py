from __future__ import annotations

from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(
        self,
        model_size: str = "medium",
        language: str | None = "pt",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
        vad_filter: bool = True,
        download_root: str | Path | None = None,
    ) -> None:
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter

        resolved_device = device
        resolved_compute = compute_type
        if device == "auto":
            try:
                import ctranslate2
                resolved_device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                resolved_device = "cpu"
        if compute_type == "auto":
            resolved_compute = "float16" if resolved_device == "cuda" else "int8"

        self.device = resolved_device
        self.compute_type = resolved_compute

        if download_root is not None:
            root = Path(download_root)
            root.mkdir(parents=True, exist_ok=True)
            download_root = str(root)

        self.model = WhisperModel(
            model_size,
            device=resolved_device,
            compute_type=resolved_compute,
            download_root=download_root,
        )

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak < 1e-4:
            return ""

        segments, _ = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
