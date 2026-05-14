from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import numpy as np

from meeting.audio.channel_buffer import ChannelBuffer
from meeting.audio.vad import Vad
from meeting.intelligence.types import Suggestion
from meeting.state import MeetingState, SessionId
from meeting.transcribe.turn import Speaker, Turn


@dataclass
class MeetingDeps:
    mic_capture: Any
    system_capture: Any
    pipeline: Any
    responder: Any
    summarizer: Any
    session_writer_factory: Callable[[SessionId], Any]
    live_window: Any
    question_detector: Any
    config: dict
    sample_rate: int = 16000
    audio_writer: Any | None = None  # optional


class MeetingController:
    """Wires everything together. The controller's job is purely orchestration:
    audio in -> buffers -> pipeline -> on_turn -> writer/window/intelligence.
    """

    def __init__(self, deps: MeetingDeps) -> None:
        self.deps = deps
        self.state = MeetingState.IDLE
        self.session_id: SessionId | None = None
        self._writer = None

        self._vad_them = Vad(silence_ms=int(deps.config.get("audio", {}).get("vad_silence_ms", 800)))
        self._vad_you = Vad(silence_ms=int(deps.config.get("audio", {}).get("vad_silence_ms", 800)))
        self._buf_them = ChannelBuffer(Speaker.THEM, on_chunk=self._on_chunk)
        self._buf_you = ChannelBuffer(Speaker.YOU, on_chunk=self._on_chunk)

        self._turns: list[Turn] = []
        self._recent_them_audio: deque[np.ndarray] = deque(maxlen=10)
        self._lock = threading.Lock()

    # ---- lifecycle ----

    def start(self) -> None:
        self.session_id = SessionId.now()
        self._writer = self.deps.session_writer_factory(self.session_id)
        self._writer.start()

        self.deps.pipeline.start()

        self.deps.mic_capture.on_audio = self._on_mic_audio
        self.deps.system_capture.on_audio = self._on_sys_audio

        self.deps.mic_capture.open()
        self.deps.system_capture.open()

        self.state = MeetingState.RECORDING

    def stop(self, on_progress: "Callable[[str], None] | None" = None) -> "dict | None":
        """Encerra a reunião. Etapas síncronas:
          1. fecha capturas, 2. flush buffers, 3. drena pipeline, 4. transcreve
          o que sobrou, 5. gera sumário via LLM, 6. grava sumario.md.

        Retorna dict com info da sessão (dir + arquivos) ou None se nunca rodou.
        Se on_progress for passado, é chamado a cada etapa com mensagem em pt-BR.
        """
        if self.state is MeetingState.STOPPED:
            return None

        def progress(msg: str) -> None:
            if on_progress is not None:
                try:
                    on_progress(msg)
                except Exception:
                    pass

        progress("Fechando microfone…")
        try: self.deps.mic_capture.close()
        except Exception: pass

        progress("Fechando captura do sistema…")
        try: self.deps.system_capture.close()
        except Exception: pass

        progress("Finalizando áudio pendente…")
        try: self._buf_them.on_turn_end()
        except Exception: pass
        try: self._buf_you.on_turn_end()
        except Exception: pass

        progress("Transcrevendo trechos finais…")
        try: self.deps.pipeline.stop()
        except Exception: pass

        progress("Gerando sumário com LLM…")
        try:
            summary = self.deps.summarizer.summarize(self._turns)
        except Exception as e:
            summary = f"## Resumo\n_Falha ao gerar sumário: {e}_\n"

        progress("Salvando arquivos…")
        session_dir = None
        if self._writer is not None:
            try:
                self._writer.finalize(summary=summary)
                session_dir = self._writer.dir
            except Exception:
                pass

        self.state = MeetingState.STOPPED

        if session_dir is None:
            return None

        return {
            "session_dir": session_dir,
            "files": {
                "transcript.txt": session_dir / "transcript.txt",
                "sumario.md": session_dir / "sumario.md",
            },
            "n_turns": len(self._turns),
        }

    # ---- audio callbacks ----

    def _on_mic_audio(self, chunk: np.ndarray) -> None:
        if self.state is not MeetingState.RECORDING:
            return
        self._buf_you.feed_audio(chunk)
        for ev in self._vad_you.feed(chunk):
            if ev == "turn_end":
                self._buf_you.on_turn_end()

    def _on_sys_audio(self, chunk: np.ndarray) -> None:
        if self.state is not MeetingState.RECORDING:
            return
        self._buf_them.feed_audio(chunk)
        self._recent_them_audio.append(chunk)
        for ev in self._vad_them.feed(chunk):
            if ev == "turn_end":
                self._buf_them.on_turn_end()

    def _on_chunk(self, speaker: Speaker, audio: np.ndarray) -> None:
        self.deps.pipeline.submit(speaker, audio)

    # ---- turn handling ----

    def _on_turn(self, turn: Turn) -> None:
        with self._lock:
            self._turns.append(turn)
        if self._writer is not None:
            try:
                self._writer.append_turn(turn)
            except Exception:
                pass
        try:
            self.deps.live_window.append_turn(turn)
        except Exception:
            pass

        if turn.speaker is Speaker.THEM and self.deps.config.get("intelligence", {}).get("question_detection", True):
            tail = np.concatenate(list(self._recent_them_audio)) if self._recent_them_audio else None
            if self.deps.question_detector.is_question(turn.text, tail):
                if self.deps.config["intelligence"].get("auto_suggest", True):
                    threading.Thread(target=self._respond_async, args=(turn,), daemon=True).start()

    def _respond_async(self, turn: Turn) -> None:
        recent = self._recent_context()
        try:
            suggestion: Suggestion = self.deps.responder.respond(
                question=turn.text, recent_context=recent
            )
        except Exception:
            return
        ttl = int(self.deps.config["intelligence"].get("suggestion_ttl_seconds", 90))
        try:
            self.deps.live_window.show_suggestion(suggestion, ttl_seconds=ttl)
        except Exception:
            pass

    def _recent_context(self) -> str:
        minutes = int(self.deps.config["intelligence"].get("context_window_minutes", 2))
        if not self._turns:
            return ""
        cutoff = datetime.now()
        cutoff_ts = cutoff.timestamp() - minutes * 60
        recent = [t for t in self._turns if t.wall_clock.timestamp() >= cutoff_ts]
        return "\n".join(t.to_line() for t in recent)
