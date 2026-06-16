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

try:
    from src import logger as _slog
    log = _slog.get("controller")
except Exception:
    import logging as _logging
    log = _logging.getLogger("sussurro.controller")


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

        # Debug counters (logged every ~5s by a daemon timer)
        self._dbg = {
            "mic_chunks": 0, "mic_samples": 0,
            "sys_chunks": 0, "sys_samples": 0,
            "vad_you_turn_ends": 0, "vad_them_turn_ends": 0,
            "pipeline_submits": 0,
            "turns_emitted": 0,
        }
        self._dbg_timer_stop = threading.Event()

    # ---- lifecycle ----

    def start(self) -> None:
        self.session_id = SessionId.now()
        log.info("MeetingController.start · session=%s", self.session_id.value)
        self._writer = self.deps.session_writer_factory(self.session_id)
        self._writer.start()

        self.deps.pipeline.start()

        self.deps.mic_capture.on_audio = self._on_mic_audio
        self.deps.system_capture.on_audio = self._on_sys_audio

        self.deps.mic_capture.open()
        log.info("Mic capture opened")
        self.deps.system_capture.open()
        log.info("System capture opened")

        self.state = MeetingState.RECORDING

        # Heartbeat: log debug counters every 5s so we can see if audio is flowing.
        self._dbg_timer_stop.clear()
        threading.Thread(target=self._dbg_heartbeat, daemon=True).start()

    def start_from_file(
        self,
        path: "Path",
        on_progress: "Callable[[float, str], None] | None" = None,
    ) -> None:
        """Transcribe a media file (mp3/mp4/wav/etc) through the same pipeline,
        without opening mic/loopback. All turns are tagged as Speaker.THEM.

        Runs synchronously: returns when every chunk has been pushed to the
        pipeline. The caller should then call stop() to finalize transcription
        (drain pool, generate summary, save files).

        on_progress(percent, message) is called as chunks are dispatched.
        """
        from pathlib import Path as _P
        from meeting.audio.file_source import iter_chunks, probe_duration_seconds
        path = _P(path)
        log.info("start_from_file · %s", path)

        self.session_id = SessionId.now()
        self._writer = self.deps.session_writer_factory(self.session_id)
        self._writer.start()
        self.deps.pipeline.start()
        self.state = MeetingState.RECORDING

        duration = probe_duration_seconds(path)
        log.info("File duration: %.1fs", duration)

        elapsed = 0.0
        chunk_seconds = 30.0
        for chunk in iter_chunks(path, chunk_seconds=chunk_seconds):
            seconds = chunk.size / 16000
            self._dbg["pipeline_submits"] += 1
            log.info("File chunk · %.2fs (cumulative %.1f/%.1f)", seconds, elapsed + seconds, duration)
            self.deps.pipeline.submit(Speaker.THEM, chunk)
            elapsed += seconds
            if on_progress and duration > 0:
                pct = min(0.99, elapsed / duration)
                on_progress(pct, f"Lendo arquivo · {int(pct*100)}%")
            elif on_progress:
                on_progress(0.0, f"Lendo arquivo · {elapsed:.0f}s lidos")

        if on_progress:
            on_progress(0.99, "Aguardando transcrição dos últimos chunks…")
        log.info("All file chunks dispatched · %.1fs of audio", elapsed)

    def _dbg_heartbeat(self) -> None:
        last_snapshot = dict(self._dbg)
        while not self._dbg_timer_stop.wait(5.0):
            cur = dict(self._dbg)
            delta = {k: cur[k] - last_snapshot.get(k, 0) for k in cur}
            log.info(
                "HEARTBEAT · mic +%d chunks (+%.1fs) · sys +%d chunks (+%.1fs) · "
                "vad_end you=%d them=%d · submits=%d · turns=%d",
                delta["mic_chunks"], delta["mic_samples"] / 16000,
                delta["sys_chunks"], delta["sys_samples"] / 16000,
                delta["vad_you_turn_ends"], delta["vad_them_turn_ends"],
                delta["pipeline_submits"], delta["turns_emitted"],
            )
            last_snapshot = cur

    def stop(self, on_progress: "Callable[[str], None] | None" = None) -> "dict | None":
        """Encerra a reunião. Etapas síncronas:
          1. fecha capturas, 2. flush buffers, 3. drena pipeline, 4. transcreve
          o que sobrou, 5. gera sumário via LLM, 6. grava sumario.md.

        Retorna dict com info da sessão (dir + arquivos) ou None se nunca rodou.
        Se on_progress for passado, é chamado a cada etapa com mensagem em pt-BR.
        """
        if self.state is MeetingState.STOPPED:
            return None

        self._dbg_timer_stop.set()
        log.info(
            "Final counters · mic=%d chunks/%.1fs · sys=%d chunks/%.1fs · "
            "vad_end you=%d them=%d · submits=%d · turns=%d",
            self._dbg["mic_chunks"], self._dbg["mic_samples"] / 16000,
            self._dbg["sys_chunks"], self._dbg["sys_samples"] / 16000,
            self._dbg["vad_you_turn_ends"], self._dbg["vad_them_turn_ends"],
            self._dbg["pipeline_submits"], self._dbg["turns_emitted"],
        )

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
        self._dbg["mic_chunks"] += 1
        self._dbg["mic_samples"] += int(chunk.size)
        self._buf_you.feed_audio(chunk)
        for ev in self._vad_you.feed(chunk):
            if ev == "turn_end":
                self._dbg["vad_you_turn_ends"] += 1
                log.debug("VAD you turn_end")
                self._buf_you.on_turn_end()

    def _on_sys_audio(self, chunk: np.ndarray) -> None:
        if self.state is not MeetingState.RECORDING:
            return
        self._dbg["sys_chunks"] += 1
        self._dbg["sys_samples"] += int(chunk.size)
        self._buf_them.feed_audio(chunk)
        self._recent_them_audio.append(chunk)
        for ev in self._vad_them.feed(chunk):
            if ev == "turn_end":
                self._dbg["vad_them_turn_ends"] += 1
                log.debug("VAD them turn_end")
                self._buf_them.on_turn_end()

    def _on_chunk(self, speaker: Speaker, audio: np.ndarray) -> None:
        self._dbg["pipeline_submits"] += 1
        log.info(
            "Submitting chunk to pipeline · speaker=%s · samples=%d · seconds=%.2f",
            speaker.value, audio.size, audio.size / 16000,
        )
        self.deps.pipeline.submit(speaker, audio)

    # ---- turn handling ----

    def _on_turn(self, turn: Turn) -> None:
        self._dbg["turns_emitted"] += 1
        log.info(
            "TURN · speaker=%s · text=%r · %.2fs..%.2fs",
            turn.speaker.value, turn.text[:120], turn.start, turn.end,
        )
        with self._lock:
            self._turns.append(turn)
        if self._writer is not None:
            try:
                self._writer.append_turn(turn)
            except Exception:
                log.exception("writer.append_turn failed")
        try:
            self.deps.live_window.append_turn(turn)
        except Exception:
            log.exception("live_window.append_turn failed")

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
