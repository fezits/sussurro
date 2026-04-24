from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable


MODEL_SIZES_BYTES = {
    "tiny": 75_000_000,
    "tiny.en": 75_000_000,
    "base": 145_000_000,
    "base.en": 145_000_000,
    "small": 485_000_000,
    "small.en": 485_000_000,
    "medium": 1_530_000_000,
    "medium.en": 1_530_000_000,
    "large-v1": 3_090_000_000,
    "large-v2": 3_090_000_000,
    "large-v3": 3_090_000_000,
}


def model_dir_for(root: Path, model_size: str) -> Path:
    """Path where faster-whisper / huggingface_hub will download the snapshot."""
    name = f"models--Systran--faster-whisper-{model_size}"
    return root / name


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0
    return total


def is_model_complete(root: Path, model_size: str) -> bool:
    d = model_dir_for(root, model_size)
    snapshots = d / "snapshots"
    if not snapshots.exists():
        return False
    try:
        for snap in snapshots.iterdir():
            bin_files = list(snap.glob("*.bin"))
            if not bin_files:
                continue
            for bf in bin_files:
                try:
                    if bf.is_file() and bf.stat().st_size > 1_000_000:
                        return True
                except OSError:
                    continue
    except OSError:
        return False
    return False


class DownloadMonitor:
    """Polls the model directory size and emits progress callbacks.

    faster-whisper uses snapshot_download which doesn't expose progress.
    We estimate % from disk growth vs. a known expected size.
    """

    def __init__(
        self,
        root: Path,
        model_size: str,
        on_progress: Callable[[float, str], None],
        interval: float = 0.5,
    ) -> None:
        self.root = Path(root)
        self.model_size = model_size
        self.on_progress = on_progress
        self.interval = interval
        self.expected_bytes = MODEL_SIZES_BYTES.get(model_size, 1_500_000_000)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _fmt_mb(self, n: int) -> str:
        return f"{n / 1_048_576:.0f} MB"

    def _run(self) -> None:
        dir_path = model_dir_for(self.root, self.model_size)
        last_size = -1
        stagnation_ticks = 0
        while not self._stop.is_set():
            size = _dir_size(dir_path)
            if size > last_size:
                stagnation_ticks = 0
            else:
                stagnation_ticks += 1
            last_size = size

            if size == 0:
                pct = 0.0
                label = f"Conectando ao servidor…"
            else:
                pct = min(0.99, size / self.expected_bytes)
                label = f"Baixando modelo {self.model_size} · {self._fmt_mb(size)} / {self._fmt_mb(self.expected_bytes)}"
            try:
                self.on_progress(pct, label)
            except Exception:
                pass

            if self._stop.wait(self.interval):
                break

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
