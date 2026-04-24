from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import yaml
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from src.download_monitor import DownloadMonitor, is_model_complete
from src.hotkey import PressToTalk
from src.injector import paste_text
from src.overlay import OrbOverlay, OverlayState
from src.recorder import Recorder
from src.transcriber import Transcriber


MIN_RECORDING_SECONDS = 0.25


class SussurroApp(QObject):
    state_changed = Signal(object, str, object)

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config = self._load_config(config_path)

        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        audio_cfg = self.config["audio"]
        self.recorder = Recorder(
            sample_rate=audio_cfg["sample_rate"],
            channels=audio_cfg["channels"],
            prebuffer_seconds=float(audio_cfg.get("prebuffer_seconds", 0.6)),
        )
        self.recorder.open()
        self.overlay = OrbOverlay(
            size=self.config["overlay"]["size"],
            level_provider=lambda: self.recorder.level,
        )
        self.overlay.quit_requested.connect(self._quit)
        self.overlay.show()

        self.state_changed.connect(self._apply_state_on_ui, Qt.ConnectionType.QueuedConnection)

        self.transcriber: Transcriber | None = None
        self._recording_started_at: float | None = None
        self._busy = False
        self._download_monitor: DownloadMonitor | None = None

        self.hotkey = PressToTalk(
            combo=self.config["hotkey"]["combo"],
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
        )

        self._set_state(OverlayState.LOADING, "Iniciando…")
        threading.Thread(target=self._load_model_thread, daemon=True).start()

    @staticmethod
    def _load_config(path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def _resolve_models_dir(configured: str | None) -> Path:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent.parent
        raw = configured or "models"
        p = Path(raw)
        return p if p.is_absolute() else (base / p)

    def _load_model_thread(self) -> None:
        try:
            w = self.config["whisper"]
            models_dir = self._resolve_models_dir(w.get("model_dir"))
            size = w["model"]

            if is_model_complete(models_dir, size):
                self._set_state(OverlayState.LOADING, f"Carregando modelo {size}…")
            else:
                self._set_state(
                    OverlayState.LOADING,
                    f"Preparando download…",
                    progress=0.0,
                )
                self._download_monitor = DownloadMonitor(
                    root=models_dir,
                    model_size=size,
                    on_progress=lambda pct, label: self._set_state(
                        OverlayState.LOADING, label, progress=pct
                    ),
                )
                self._download_monitor.start()

            self.transcriber = Transcriber(
                model_size=size,
                language=w.get("language"),
                device=w.get("device", "auto"),
                compute_type=w.get("compute_type", "auto"),
                beam_size=int(w.get("beam_size", 5)),
                vad_filter=bool(w.get("vad_filter", True)),
                download_root=models_dir,
            )

            if self._download_monitor is not None:
                self._download_monitor.stop()
                self._download_monitor = None

            self._set_state(OverlayState.LOADING, "Inicializando motor…", progress=None)
            dev = self.transcriber.device
            self.hotkey.start()
            self._set_state(OverlayState.IDLE, f"Pronto · Ctrl+Win p/ falar")
        except Exception as e:
            if self._download_monitor is not None:
                self._download_monitor.stop()
                self._download_monitor = None
            traceback.print_exc()
            self._set_state(OverlayState.ERROR, f"Erro: {e}")

    def _set_state(self, state: OverlayState, text: str, progress: float | None = None) -> None:
        self.state_changed.emit(state, text, progress)

    def _apply_state_on_ui(self, state: OverlayState, text: str, progress: object) -> None:
        self.overlay.set_state(state, text, progress=progress if isinstance(progress, (int, float)) else None)

    def _on_hotkey_press(self) -> None:
        if self.transcriber is None or self._busy:
            return
        if self.recorder.is_recording:
            return
        try:
            self.recorder.start()
            self._recording_started_at = time.monotonic()
            self._set_state(OverlayState.RECORDING, "Gravando…")
        except Exception as e:
            traceback.print_exc()
            self._set_state(OverlayState.ERROR, f"Erro mic: {e}")

    def _on_hotkey_release(self) -> None:
        if not self.recorder.is_recording:
            return
        try:
            audio = self.recorder.stop()
        except Exception as e:
            traceback.print_exc()
            self._set_state(OverlayState.ERROR, f"Erro mic: {e}")
            return

        duration = 0.0
        if self._recording_started_at is not None:
            duration = time.monotonic() - self._recording_started_at
        self._recording_started_at = None

        if duration < MIN_RECORDING_SECONDS or audio.size == 0:
            self._set_state(OverlayState.IDLE, "Muito curto")
            return

        self._busy = True
        self._set_state(OverlayState.TRANSCRIBING, "Transcrevendo…")
        threading.Thread(target=self._transcribe_and_inject, args=(audio,), daemon=True).start()

    def _transcribe_and_inject(self, audio: np.ndarray) -> None:
        try:
            text = self.transcriber.transcribe(audio) if self.transcriber else ""
            text = (text or "").strip()
            if not text:
                self._set_state(OverlayState.IDLE, "Nada reconhecido")
                return
            inj = self.config["inject"]
            paste_text(
                text,
                restore_clipboard=bool(inj.get("restore_clipboard", True)),
                trailing_space=bool(inj.get("trailing_space", True)),
            )
            preview = text if len(text) <= 40 else text[:37] + "…"
            self._set_state(OverlayState.IDLE, f"✓ {preview}")
        except Exception as e:
            traceback.print_exc()
            self._set_state(OverlayState.ERROR, f"Erro: {e}")
        finally:
            self._busy = False

    def _quit(self) -> None:
        try:
            self.hotkey.stop()
        except Exception:
            pass
        try:
            if self.recorder.is_recording:
                self.recorder.stop()
        except Exception:
            pass
        try:
            self.recorder.close()
        except Exception:
            pass
        self.qt_app.quit()

    def run(self) -> int:
        return self.qt_app.exec()
