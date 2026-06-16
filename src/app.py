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

from src import logger as sussurro_logger
from src.download_monitor import DownloadMonitor, is_model_complete
from src.hotkey import PressToTalk
from src.injector import paste_text
from src.overlay import OrbOverlay, OverlayState
from src.recorder import Recorder
from src.transcriber import Transcriber

log = sussurro_logger.get("app")


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
        self.overlay.meeting_toggle_requested.connect(self._toggle_meeting)
        self.overlay.transcribe_file_requested.connect(self._transcribe_file)
        self._meeting_controller = None
        self._meeting_window = None
        self._stopping_meeting = False
        self.meeting_stop_progress.connect(
            self._on_meeting_stop_progress, Qt.ConnectionType.QueuedConnection
        )
        self.meeting_stop_finished.connect(
            self._on_meeting_stop_finished, Qt.ConnectionType.QueuedConnection
        )
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
            log.info("Whisper ready · device=%s · starting hotkey listener", dev)
            self.hotkey.start()
            log.info("Hotkey listener started · combo=%s", self.config["hotkey"]["combo"])
            self._set_state(OverlayState.IDLE, f"Pronto · Ctrl+Win p/ falar")
            log.info("=== App READY (dictation active, meeting menu enabled) ===")
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
        log.info("HOTKEY press · transcriber_ready=%s · busy=%s · recording=%s",
                 self.transcriber is not None, self._busy, self.recorder.is_recording)
        if self.transcriber is None or self._busy:
            log.info("Hotkey ignored (transcriber=None or busy)")
            return
        if self.recorder.is_recording:
            log.info("Hotkey ignored (already recording)")
            return
        try:
            self.recorder.start()
            self._recording_started_at = time.monotonic()
            self._set_state(OverlayState.RECORDING, "Gravando…")
            log.info("Dictation recording STARTED")
        except Exception as e:
            log.exception("Dictation start FAILED")
            traceback.print_exc()
            self._set_state(OverlayState.ERROR, f"Erro mic: {e}")

    def _on_hotkey_release(self) -> None:
        log.info("HOTKEY release · recording=%s", self.recorder.is_recording)
        if not self.recorder.is_recording:
            return
        try:
            audio = self.recorder.stop()
            log.info("Dictation stop · audio %.2fs (%d samples)", audio.size/16000, audio.size)
        except Exception as e:
            log.exception("Dictation stop FAILED")
            traceback.print_exc()
            self._set_state(OverlayState.ERROR, f"Erro mic: {e}")
            return

        duration = 0.0
        if self._recording_started_at is not None:
            duration = time.monotonic() - self._recording_started_at
        self._recording_started_at = None

        if duration < MIN_RECORDING_SECONDS or audio.size == 0:
            log.info("Dictation discarded · too short (%.2fs, %d samples)", duration, audio.size)
            self._set_state(OverlayState.IDLE, "Muito curto")
            return

        self._busy = True
        self._set_state(OverlayState.TRANSCRIBING, "Transcrevendo…")
        log.info("Dispatching dictation to transcriber thread")
        threading.Thread(target=self._transcribe_and_inject, args=(audio,), daemon=True).start()

    def _transcribe_and_inject(self, audio: np.ndarray) -> None:
        try:
            log.info("Dictation transcribe · %.2fs", audio.size/16000)
            text = self.transcriber.transcribe(audio) if self.transcriber else ""
            text = (text or "").strip()
            log.info("Dictation transcribed · text=%r", text[:120])
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

    def _toggle_meeting(self) -> None:
        log.info("=== MEETING TOGGLE clicked === · controller=%s · transcriber_ready=%s",
                 self._meeting_controller, self.transcriber is not None)
        if self._meeting_controller is None or self._meeting_controller.state.value == "stopped":
            try:
                self._start_meeting()
            except Exception as e:
                log.exception("Falha em _start_meeting")
                short = str(e).split("\n", 1)[0][:120] or e.__class__.__name__
                self._set_state(OverlayState.ERROR, f"Reunião: {short}")
                # If the LiveWindow was opened before the failure, close it.
                if self._meeting_window is not None:
                    try: self._meeting_window.close()
                    except Exception: pass
                    self._meeting_window = None
                if self._meeting_controller is not None:
                    try: self._meeting_controller.stop()
                    except Exception: pass
                    self._meeting_controller = None
                self.overlay.set_meeting_active(False)
        else:
            self._stop_meeting()

    def _start_meeting(self) -> None:
        log.info("--- Starting meeting mode ---")

        log.debug("Importing meeting modules...")
        from pathlib import Path
        import os
        import yaml

        from meeting.audio.mic_capture import MicCapture
        from meeting.audio.system_capture import SystemCapture
        from meeting.controller import MeetingController, MeetingDeps
        from meeting.intelligence.classifier import Classifier
        from meeting.intelligence.llm_client import LlmClient, LlmConfig
        from meeting.intelligence.question_detector import QuestionDetector
        from meeting.intelligence.rag.indexer import RagIndexer
        from meeting.intelligence.rag.retriever import RagRetriever
        from meeting.intelligence.responder import Responder
        from meeting.intelligence.summarizer import Summarizer
        from meeting.persistence.session_writer import SessionWriter
        from meeting.transcribe.adapter import MeetingTranscriber
        from meeting.transcribe.pipeline import TranscribePipeline
        from meeting.ui.live_window import LiveWindow
        log.debug("Imports OK")

        # Resolve config + paths (same logic as Whisper model resolution)
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent.parent

        # PyInstaller bundles datas under _internal/, but writable user paths
        # (models/, knowledge/, reunioes/) live next to the exe. Try both.
        cfg_candidates = [
            base / "meeting" / "meeting_config.yaml",
            base / "_internal" / "meeting" / "meeting_config.yaml",
        ]
        cfg_path = next((p for p in cfg_candidates if p.exists()), cfg_candidates[0])
        log.info("Loading meeting config from %s", cfg_path)
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        log.debug("Config: %s", config)

        # Validate API key early
        api_key_env = config["llm"]["api_key_env"]
        if not os.environ.get(api_key_env, "").strip():
            raise RuntimeError(
                f"Variável de ambiente {api_key_env} não definida. "
                f"Configure no Windows: setx {api_key_env} \"<sua-chave>\" e reinicie."
            )
        log.info("API key %s detected (length=%d)", api_key_env, len(os.environ[api_key_env]))

        models_dir = base / config.get("transcribe", {}).get("model_dir", "models")
        knowledge_dir = base / config["rag"]["knowledge_dir"]
        output_dir = base / config["storage"]["output_dir"]
        log.info("Paths · models=%s · knowledge=%s · output=%s", models_dir, knowledge_dir, output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # First-run: scaffold knowledge/ next to the exe so the user can edit it.
        if not knowledge_dir.exists():
            log.info("First run · creating knowledge dir + perfil.md template")
            knowledge_dir.mkdir(parents=True, exist_ok=True)
            (knowledge_dir / "perfil.md").write_text(
                "# Meu perfil\n\nEdite este arquivo livremente.\n"
                "O Sussurro usa o conteúdo como contexto pra responder perguntas sobre você.\n",
                encoding="utf-8",
            )

        self._set_state(OverlayState.LOADING, "Carregando Whisper…")
        log.info("Building MeetingTranscriber (model=%s)", config["transcribe"]["model"])
        transcriber = MeetingTranscriber(
            model_size=config["transcribe"]["model"],
            language=config["transcribe"]["language"],
            download_root=models_dir,
        )
        log.info("MeetingTranscriber ready · device=%s", transcriber.device)

        pipeline = TranscribePipeline(
            transcriber=transcriber,
            on_turn=lambda t: None,
            workers=config["transcribe"]["parallel_workers"],
        )

        log.info("Building LLM clients (provider=%s, model=%s)", config["llm"]["provider"], config["llm"]["model"])
        llm_main = LlmClient(LlmConfig(
            provider=config["llm"]["provider"],
            model=config["llm"]["model"],
            api_key_env=api_key_env,
            local_model_path=config["llm"].get("local", {}).get("model_path"),
        ))
        llm_classifier = LlmClient(LlmConfig(
            provider=config["llm"]["provider"],
            model=config["llm"]["classifier_model"],
            api_key_env=api_key_env,
            max_tokens=4,
        ))

        self._set_state(OverlayState.LOADING, "Carregando embeddings…")
        log.info("Loading SentenceTransformer (%s)", config["rag"]["embedding_model"])
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer(config["rag"]["embedding_model"])
        log.info("Embedder ready")

        log.info("Indexing knowledge dir %s", knowledge_dir)
        indexer = RagIndexer(
            knowledge_dir=knowledge_dir,
            embedder=embedder,
            chunk_size=config["rag"]["chunk_size"],
            overlap=config["rag"]["chunk_overlap"],
        )
        try:
            n_chunks = indexer.build_or_load()
            log.info("RAG index ready · %d chunks (cached=%s)", n_chunks, indexer.was_cached_last_call)
        except Exception:
            log.exception("RAG indexing failed; continuing with empty index")
            indexer.chunks = []
        retriever = RagRetriever(indexer.chunks, embedder)
        classifier = Classifier(llm=llm_classifier, model=config["llm"]["classifier_model"])
        responder = Responder(
            retriever=retriever,
            classifier=classifier.classify,
            llm=llm_main,
            model=config["llm"]["model"],
            top_k=config["rag"]["top_k"],
        )
        summarizer = Summarizer(llm=llm_main, model=config["llm"]["model"])

        log.info("Opening LiveWindow")
        self._meeting_window = LiveWindow(opacity=config["ui"]["opacity"])
        self._meeting_window.closed.connect(self._on_live_window_closed)
        self._meeting_window.show()

        log.info("Building audio captures")
        try:
            mic = MicCapture()
        except Exception:
            log.exception("MicCapture init failed")
            raise
        try:
            sys_cap = SystemCapture()
        except Exception:
            log.exception("SystemCapture init failed (WASAPI loopback unavailable?)")
            raise

        deps = MeetingDeps(
            mic_capture=mic,
            system_capture=sys_cap,
            pipeline=pipeline,
            responder=responder,
            summarizer=summarizer,
            session_writer_factory=lambda sid: SessionWriter(
                root=output_dir,
                session_id=sid,
            ),
            live_window=self._meeting_window,
            question_detector=QuestionDetector(),
            config=config,
        )
        self._meeting_controller = MeetingController(deps)
        pipeline.on_turn = self._meeting_controller._on_turn

        self._meeting_window.pause_requested.connect(self._noop)
        self._meeting_window.stop_requested.connect(self._stop_meeting)
        self._meeting_window.force_suggest_requested.connect(self._force_suggest)

        log.info("Starting MeetingController")
        self._meeting_controller.start()
        self.overlay.set_meeting_active(True)
        self._set_state(OverlayState.RECORDING, "Reunião ativa")
        log.info("--- Meeting mode RUNNING ---")

    def _transcribe_file(self) -> None:
        """Pick a media file and transcribe it through the same pipeline.
        Reuses the meeting LiveWindow + SessionWriter + Summarizer, but
        skips mic/loopback capture.
        """
        log.info("=== TRANSCRIBE FILE clicked ===")
        if self._meeting_controller is not None:
            log.info("Meeting active; ignoring file transcribe request")
            self._set_state(OverlayState.ERROR, "Pare a reunião ativa primeiro")
            return
        if self.transcriber is None:
            log.info("Transcriber not ready yet")
            self._set_state(OverlayState.ERROR, "Aguarde o modelo carregar")
            return

        from PySide6.QtWidgets import QFileDialog
        filters = (
            "Áudio/Vídeo (*.mp3 *.mp4 *.wav *.m4a *.ogg *.webm *.mkv *.aac *.flac);;"
            "Todos os arquivos (*)"
        )
        file_str, _ = QFileDialog.getOpenFileName(
            None, "Escolha arquivo para transcrever", "", filters
        )
        if not file_str:
            log.info("File dialog cancelled")
            return

        file_path = Path(file_str)
        log.info("File selected: %s", file_path)
        threading.Thread(
            target=self._transcribe_file_worker, args=(file_path,), daemon=True
        ).start()

    def _transcribe_file_worker(self, file_path: Path) -> None:
        try:
            from pathlib import Path as _P
            import yaml
            from meeting.controller import MeetingController, MeetingDeps
            from meeting.intelligence.classifier import Classifier
            from meeting.intelligence.llm_client import LlmClient, LlmConfig
            from meeting.intelligence.question_detector import QuestionDetector
            from meeting.intelligence.rag.indexer import RagIndexer
            from meeting.intelligence.rag.retriever import RagRetriever
            from meeting.intelligence.responder import Responder
            from meeting.intelligence.summarizer import Summarizer
            from meeting.persistence.session_writer import SessionWriter
            from meeting.transcribe.adapter import MeetingTranscriber
            from meeting.transcribe.pipeline import TranscribePipeline
            from meeting.ui.live_window import LiveWindow

            if getattr(sys, "frozen", False):
                base = _P(sys.executable).resolve().parent
            else:
                base = _P(__file__).resolve().parent.parent
            cfg_candidates = [
                base / "meeting" / "meeting_config.yaml",
                base / "_internal" / "meeting" / "meeting_config.yaml",
            ]
            cfg_path = next((p for p in cfg_candidates if p.exists()), cfg_candidates[0])
            config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

            models_dir = base / "models"
            output_dir = base / config["storage"]["output_dir"]
            output_dir.mkdir(parents=True, exist_ok=True)

            self._set_state(OverlayState.LOADING, f"Abrindo {file_path.name}…")
            transcriber = MeetingTranscriber(
                model_size=config["transcribe"]["model"],
                language=config["transcribe"]["language"],
                download_root=models_dir,
            )
            pipeline = TranscribePipeline(
                transcriber=transcriber,
                on_turn=lambda t: None,
                workers=config["transcribe"]["parallel_workers"],
            )

            # Summarizer is required at stop(); use a stub LLM if Groq missing.
            api_key_env = config["llm"]["api_key_env"]
            import os as _os
            has_key = bool(_os.environ.get(api_key_env, "").strip())
            if has_key:
                llm_main = LlmClient(LlmConfig(
                    provider=config["llm"]["provider"],
                    model=config["llm"]["model"],
                    api_key_env=api_key_env,
                ))
                summarizer = Summarizer(llm=llm_main, model=config["llm"]["model"])
            else:
                log.warning("No %s set; skipping LLM summary", api_key_env)
                class _NoLlm:
                    def complete(self, _messages): return "## Resumo\n_Sem chave LLM configurada._\n"
                summarizer = Summarizer(llm=_NoLlm(), model="none")

            self._meeting_window = LiveWindow(opacity=config["ui"]["opacity"])
            self._meeting_window.closed.connect(self._on_live_window_closed)
            self._meeting_window.stop_requested.connect(self._stop_meeting)
            self._meeting_window.pause_requested.connect(self._noop)
            self._meeting_window.force_suggest_requested.connect(self._noop)
            self._meeting_window.show()

            deps = MeetingDeps(
                mic_capture=None,
                system_capture=None,
                pipeline=pipeline,
                responder=None,
                summarizer=summarizer,
                session_writer_factory=lambda sid: SessionWriter(
                    root=output_dir,
                    session_id=sid,
                ),
                live_window=self._meeting_window,
                question_detector=QuestionDetector(),
                config=config,
            )
            self._meeting_controller = MeetingController(deps)
            pipeline.on_turn = self._meeting_controller._on_turn
            self.overlay.set_meeting_active(True)

            def progress(pct: float, msg: str) -> None:
                # Marshalled via signal so UI updates safely.
                self.meeting_stop_progress.emit(msg)

            self._meeting_window.show_finalization_status(f"Transcrevendo {file_path.name}…")
            log.info("Starting file transcription · %s", file_path)
            self._meeting_controller.start_from_file(file_path, on_progress=progress)
            log.info("File chunks dispatched, calling stop() to drain pipeline + summarize")

            # Re-use the normal stop() path: drains pipeline, summary, save files.
            self._stop_meeting()
        except Exception:
            log.exception("Falha em _transcribe_file_worker")
            self._set_state(OverlayState.ERROR, "Erro ao transcrever arquivo")
            self._stopping_meeting = False
            if self._meeting_window is not None:
                try: self._meeting_window.close()
                except Exception: pass
                self._meeting_window = None
            self._meeting_controller = None
            self.overlay.set_meeting_active(False)

    def _force_suggest(self) -> None:
        if self._meeting_controller is None:
            return
        last_them = next(
            (t for t in reversed(self._meeting_controller._turns) if t.speaker.value == "Eles"),
            None,
        )
        if last_them is None:
            return
        threading.Thread(
            target=self._meeting_controller._respond_async, args=(last_them,), daemon=True
        ).start()

    # Signals to marshal stop() progress back to the UI thread.
    meeting_stop_progress = Signal(str)
    meeting_stop_finished = Signal(object)  # dict | None

    def _stop_meeting(self) -> None:
        """Stop the meeting WITHOUT closing the app or the live window.
        Runs the slow finalization (Whisper draining, LLM summary, file
        write) in a background thread and reports progress to the live
        window. The user closes the window themselves when ready.
        """
        if self._meeting_controller is None:
            return
        if self._stopping_meeting:
            log.debug("Stop already in progress; ignoring")
            return
        self._stopping_meeting = True

        controller = self._meeting_controller
        window = self._meeting_window
        log.info("Stopping meeting…")
        self.overlay.set_meeting_active(False)
        self._set_state(OverlayState.TRANSCRIBING, "Finalizando reunião…")

        if window is not None:
            try: window.show_finalization_status("Finalizando reunião…")
            except Exception: pass

        def progress(msg: str) -> None:
            self.meeting_stop_progress.emit(msg)

        def worker() -> None:
            result = None
            try:
                result = controller.stop(on_progress=progress)
            except Exception:
                log.exception("Falha em controller.stop")
            self.meeting_stop_finished.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_meeting_stop_progress(self, msg: str) -> None:
        log.info("stop progress · %s", msg)
        if self._meeting_window is not None:
            try: self._meeting_window.show_finalization_status(msg)
            except Exception: pass
        self._set_state(OverlayState.TRANSCRIBING, msg)

    def _on_live_window_closed(self) -> None:
        """Called when the user closes the LiveWindow via the X button or
        the 'Fechar' button on the finalization panel. We just drop our
        reference — Qt is already destroying the widget. The bubble overlay
        keeps the app alive."""
        log.info("LiveWindow closed by user")
        self._meeting_window = None

    def _on_meeting_stop_finished(self, result) -> None:
        log.info("Meeting stop finished · result=%s", result)
        self._stopping_meeting = False
        self._meeting_controller = None

        if isinstance(result, dict) and result.get("session_dir"):
            session_dir = result["session_dir"]
            files = result["files"]
            n_turns = result.get("n_turns", 0)
            if self._meeting_window is not None:
                try:
                    self._meeting_window.show_finalization_complete(session_dir, files)
                except Exception:
                    log.exception("Failed showing finalization panel")
            self._set_state(OverlayState.IDLE, f"✓ {n_turns} turnos · salvo em {session_dir.name}")
        else:
            self._set_state(OverlayState.IDLE, "Reunião encerrada (sem arquivos)")
            if self._meeting_window is not None:
                try: self._meeting_window.close()
                except Exception: pass
                self._meeting_window = None

    def _noop(self) -> None:
        pass

    def _quit(self) -> None:
        try:
            if self._meeting_controller is not None:
                self._stop_meeting()
        except Exception:
            pass
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
