# Sussurro — Architecture Reference

Mapa funcional do sistema. Use isto pra navegar rapidamente: cada entrada lista o que a função faz, em que arquivo está, e quem chama.

> **For Claude:** este documento é a fonte primária ao responder "o que X faz". Antes de inventar/relembrar, abre este arquivo, acha a função e responde direto. Atualize aqui quando o comportamento mudar.

## Topologia

```
SussurroApp (src/app.py)
├── OrbOverlay              ← bolinha flutuante (dictation + menu)
├── Recorder + PressToTalk  ← ditado Ctrl+Win
├── Transcriber             ← Whisper para o ditado
└── MeetingController       ← orquestrador do modo reunião (lazy)
    ├── MicCapture          ← canal "Você"
    ├── SystemCapture       ← canal "Eles" (WASAPI loopback)
    ├── Vad × 2             ← detecta fim de turno por canal
    ├── ChannelBuffer × 2   ← acumula áudio até turn_end
    ├── TranscribePipeline  ← workers paralelos (Whisper)
    ├── SessionWriter       ← grava transcript.txt em tempo real
    ├── Responder           ← classifier + RAG + LLM por pergunta
    │   ├── Classifier      ← Llama Instant: A/B/C
    │   ├── RagRetriever    ← top-k cosine sobre embeddings
    │   └── LlmClient       ← Groq por padrão
    ├── Summarizer          ← gera sumario.md no stop()
    ├── QuestionDetector    ← heurística "2-of-3"
    └── LiveWindow          ← janela invisível à captura
```

## Lifecycle de uma reunião

```
clique direito → "Iniciar reunião"
   │
   ▼
SussurroApp._toggle_meeting()                          [src/app.py:194]
   └─ SussurroApp._start_meeting()                     [src/app.py:209]
      ├─ load config, key check, instantiate everything
      └─ MeetingController.start()                     [meeting/controller.py:55]
         ├─ SessionWriter.start()                      → cria reunioes/<ts>/, trunca transcript.txt
         ├─ TranscribePipeline.start()                 → sobe thread pool
         └─ MicCapture.open() + SystemCapture.open()   → audio começa a fluir

[durante a reunião]
audio chunk → MicCapture._callback → ChannelBuffer.feed_audio + Vad.feed
                                       │
                                       └─ turn_end? → ChannelBuffer.on_turn_end → on_chunk → Pipeline.submit
                                                                                                │
Pipeline._work(audio) → Transcriber.transcribe → Turn(...) → MeetingController._on_turn
                                                                │
                                                                ├─ self._turns.append
                                                                ├─ SessionWriter.append_turn
                                                                ├─ LiveWindow.append_turn
                                                                └─ if Speaker.THEM + question → Responder.respond (thread)
                                                                                                  → LiveWindow.show_suggestion

clique "Parar" / Ctrl+Q
   │
   ▼
SussurroApp._stop_meeting()                            [src/app.py:380]
   └─ MeetingController.stop()                         [meeting/controller.py:71]
      ├─ MicCapture.close()                            → fecha stream
      ├─ SystemCapture.close()                         → fecha loopback
      ├─ ChannelBuffer.on_turn_end() × 2               → flush do áudio restante
      ├─ TranscribePipeline.stop()                     → drena fila + shutdown pool
      ├─ Summarizer.summarize(self._turns)             → chama LLM, devolve markdown
      └─ SessionWriter.finalize(summary=...)           → grava sumario.md, fecha thread

LiveWindow.close()                                     → salva geometria em .window_state.json
overlay.set_meeting_active(False)                      → menu volta a "Iniciar reunião"
state = STOPPED
```

**Resumo do "Parar reunião" em uma frase:** fecha as duas capturas de áudio, esvazia o buffer pendente, encerra o pool de transcrição, manda a transcrição completa pro LLM gerar o sumário, salva `transcript.txt` (que já vinha sendo escrito em tempo real) + `sumario.md` em `reunioes/<timestamp>/`, e fecha a janela ao vivo.

**Onde está cada artefato ao final:**
- `reunioes/<YYYY-MM-DD_HH-MM>/transcript.txt` — diálogo completo com timestamps
- `reunioes/<YYYY-MM-DD_HH-MM>/sumario.md` — sumário gerado pelo LLM
- `reunioes/<YYYY-MM-DD_HH-MM>/audio.wav` — só se `save_raw_wav: true` no config

---

## Por módulo

### `main.py` — Entry point
- **`main()`** — Carrega logger, resolve `config.yaml` (tenta `_internal/` como fallback no exe), instancia `SussurroApp`, chama `.run()`. Captura qualquer exception fatal pro log.

### `src/logger.py` — Logger persistente
- **`setup()`** [src/logger.py:21] — Configura logger root `sussurro` com `RotatingFileHandler` (2MB × 3 backups) gravando em `sussurro.log` ao lado do exe (ou raiz do projeto se não-frozen) + stderr. Idempotente.
- **`get(name)`** [src/logger.py:65] — Retorna `logging.Logger` no namespace `sussurro.<name>`.

### `src/app.py` — Orquestrador principal (ditado + integração reunião)
- **`SussurroApp.__init__`** [src/app.py:30] — Constrói `Recorder`, `OrbOverlay`, conecta sinais (`quit_requested`, `meeting_toggle_requested`), dispara thread de carregamento do modelo Whisper.
- **`_load_config(path)`** [src/app.py:72] — Lê `config.yaml`.
- **`_resolve_models_dir(configured)`** [src/app.py:77] — Resolve `models/` relativo ao exe (frozen) ou raiz do projeto.
- **`_load_model_thread()`** [src/app.py:87] — Em background: detecta se modelo existe, opcionalmente sobe `DownloadMonitor`, instancia `Transcriber` (modelo `small`), inicia `PressToTalk`. Estado final: `IDLE` "Pronto · Ctrl+Win p/ falar".
- **`_set_state(state, text, progress)`** [src/app.py:135] — Emite sinal Qt pra atualizar overlay.
- **`_apply_state_on_ui(...)`** [src/app.py:138] — Slot que repassa pro `overlay.set_state`.
- **`_on_hotkey_press()`** [src/app.py:141] — `Recorder.start()` quando segura `Ctrl+Win`.
- **`_on_hotkey_release()`** [src/app.py:154] — `Recorder.stop()`, dispara `_transcribe_and_inject` numa thread.
- **`_transcribe_and_inject(audio)`** [src/app.py:177] — Whisper transcreve, `paste_text` cola via clipboard + `Ctrl+V`, atualiza overlay com preview.
- **`_toggle_meeting()`** [src/app.py:194] — Item de menu "Iniciar/Parar reunião". Encapsula `_start_meeting` num try/except que loga falha e mostra erro na bolinha.
- **`_start_meeting()`** [src/app.py:209] — Carrega `meeting_config.yaml`, valida `GROQ_API_KEY`, monta `MeetingTranscriber` + `LlmClient` × 2 + `SentenceTransformer` + `RagIndexer/Retriever` + `Responder` + `Summarizer` + `LiveWindow` + `MicCapture` + `SystemCapture` + `MeetingController`. Chama `controller.start()`.
- **`_force_suggest()`** [src/app.py:355] — Pega o último turn `[Eles]` e dispara `responder.respond` numa thread (botão "Forçar sugestão" da janela).
- **`_stop_meeting()`** [src/app.py:368] — Chama `MeetingController.stop()`, fecha `LiveWindow`, restaura menu.
- **`_quit()`** [src/app.py:386] — Para reunião se ativa, para hotkey, fecha recorder, encerra Qt.

### `src/overlay.py` — Bolinha flutuante (`OrbOverlay`)
- **`OrbOverlay.__init__`** — Cria QWidget sempre-no-topo, frameless, translúcido. Timer de 30ms anima.
- **`set_state(state, status, progress)`** [src/overlay.py:93] — Muda cor/animação da bolinha e label embaixo. Estados: IDLE, RECORDING, TRANSCRIBING, LOADING, ERROR.
- **`paintEvent`** [src/overlay.py:106] — Desenha o orb com gradient + glow + animação interna (microfone / waveform / spinner) por estado.
- **`mousePressEvent` / `mouseMoveEvent`** — Arrasta a bolinha.
- **`contextMenuEvent`** [src/overlay.py:262] — Menu de clique direito: status, "Iniciar/Parar reunião" → emite `meeting_toggle_requested`, "Sair" → emite `quit_requested`.
- **`set_meeting_active(active)`** [src/overlay.py:278] — Atualiza texto do item de menu.

### `src/recorder.py` — Captura do ditado
- **`Recorder.__init__`** — Mantém `sounddevice.InputStream` aberto continuamente; pré-buffer rolling de 600ms.
- **`open()`** — Abre o stream.
- **`start()`** — Marca início da gravação (já estava capturando no pré-buffer).
- **`stop()`** — Retorna `np.ndarray` com o áudio gravado **incluindo o pré-buffer** (resolve o problema de "perdi a primeira palavra").
- **`close()`** — Fecha o stream.
- **`level`** (property) — RMS atual, alimenta a waveform do overlay.

### `src/hotkey.py` — `PressToTalk`
- **`start()`** — Registra hook global no `keyboard` pra detectar combo `Ctrl+Win` (config).
- **`stop()`** — Remove hooks.
- Internamente: distingue press vs release; ignora repeats; chama `on_press`/`on_release` do app.

### `src/transcriber.py` — Wrapper `faster-whisper`
- **`Transcriber.__init__`** — Resolve device (CPU/CUDA auto), compute_type (int8/float16 auto), instancia `WhisperModel` apontando pra `models/`.
- **`transcribe(audio)`** — `model.transcribe(audio, language=pt, beam_size, vad_filter)` retorna texto concatenado dos segments.

### `src/injector.py` — Cola texto
- **`paste_text(text, restore_clipboard, trailing_space)`** — Salva conteúdo atual do clipboard (opcional), copia o texto novo, simula `Ctrl+V`, restaura clipboard. Preserva acentos (Unicode via clipboard, não keystroke).

### `src/download_monitor.py` — Monitor de download do modelo Whisper
- **`is_model_complete(root, size)`** — Verifica se modelo já está em `root/models--Systran--faster-whisper-<size>/`.
- **`DownloadMonitor`** — Thread que aponta para o diretório `huggingface_hub` em progresso e emite eventos de % via callback.

---

### `meeting/state.py`
- **`MeetingState`** — Enum `IDLE | RECORDING | PAUSED | STOPPED`.
- **`SessionId`** — Dataclass com `value` string. `SessionId.now()` formata `YYYY-MM-DD_HH-MM`.

### `meeting/transcribe/turn.py`
- **`Speaker`** — Enum `YOU="Você" | THEM="Eles"`.
- **`Turn`** — Dataclass frozen `(speaker, start, end, text, wall_clock)`.
- **`Turn.to_line()`** — Render `HH:MM:SS [Speaker]   texto` (usado em `transcript.txt` e UI).

### `meeting/audio/vad.py` — Detecta fim de turno
- **`Vad.__init__(silence_ms, sample_rate)`** — Carrega silero-vad ONNX. Frame fixo 512 samples = 32ms @ 16kHz.
- **`feed(audio)`** [meeting/audio/vad.py:32] — Buffer interno, processa frame a frame. Emite string `"turn_end"` quando **estava falando E** o silêncio dura `silence_ms`. Pura silêncio sem fala prévia: nada.
- **`reset()`** — Limpa estado.

### `meeting/audio/mic_capture.py` — Canal "Você"
- **`MicCapture.__init__`** — `sample_rate=16000`, callback opcional `on_audio`.
- **`open()`** — Abre `sounddevice.InputStream` mono float32. Coexiste com `Recorder` do ditado (WASAPI shared mode permite múltiplos consumers).
- **`close()`** — Para o stream.
- **`_callback`** — Achata pra mono, copia, chama `on_audio(chunk)`.

### `meeting/audio/system_capture.py` — Canal "Eles"
- **`SystemCapture.__init__`** — Usa `pyaudiowpatch` pra acessar WASAPI loopback (saída das caixas/fone).
- **`open()`** [meeting/audio/system_capture.py:51] — Abre stream loopback no device default. Downmix stereo→mono + resample pra 16kHz dentro do callback.
- **`close()`** — Para stream + `pa.terminate()`.
- **`_callback`** — Recebe bytes, decodifica float32, mono, resample por `np.interp`, chama `on_audio`.

### `meeting/audio/channel_buffer.py` — Buffer por canal
- **`ChannelBuffer.__init__(speaker, on_chunk, sample_rate, max_seconds=30)`** — Buffer de áudio float32 acumulado por turno.
- **`feed_audio(chunk)`** — Acumula. Se passar `max_seconds`, flush automático (proteção contra fala ininterrupta).
- **`on_turn_end()`** — Flush imediato (chamado quando VAD diz "turn_end"). Vazio → no-op.
- **`_flush()`** — Concatena partes, chama `on_chunk(speaker, audio)`, limpa.

### `meeting/transcribe/pipeline.py` — Pool de workers Whisper
- **`TranscribePipeline.__init__(transcriber, on_turn, workers, sample_rate, meeting_start)`**.
- **`start()`** [meeting/transcribe/pipeline.py:46] — Cria `ThreadPoolExecutor` + thread dispatcher.
- **`submit(speaker, audio)`** — Captura `wall_clock=now()`, enfileira.
- **`_dispatch_loop()`** — Pega da fila, despacha pro pool.
- **`_work(speaker, audio, wall)`** — Whisper transcreve, monta `Turn`, chama `on_turn`.
- **`stop()`** [meeting/transcribe/pipeline.py:54] — Poison pill na fila, join dispatcher, shutdown pool.

### `meeting/transcribe/adapter.py` — `MeetingTranscriber`
- **`MeetingTranscriber.__init__`** — Wrapper sobre `src.transcriber.Transcriber` com defaults pra reunião: `beam_size=1`, `vad_filter=False` (já VADamos upstream).
- **`transcribe(audio)`** — Chama inner, strip.
- **`device`** (property) — Repasse.

### `meeting/persistence/session_writer.py` — Grava `transcript.txt` + `sumario.md`
- **`SessionWriter.__init__(root, session_id)`**.
- **`start()`** [meeting/persistence/session_writer.py:23] — Cria `reunioes/<sid>/`, trunca `transcript.txt`, sobe thread daemon que drena a fila.
- **`append_turn(turn)`** — Enfileira; thread escreve `turn.to_line() + "\n"`.
- **`flush_now(timeout=5.0)`** — Bloqueia até a fila ficar vazia (usado por tests e quando `finalize` é chamado).
- **`finalize(summary)`** [meeting/persistence/session_writer.py:38] — `flush_now()`, poison pill, join thread, grava `sumario.md`.
- **`_loop()`** — Thread daemon: lê da fila, append no arquivo, set idle event quando vazia.

### `meeting/persistence/audio_writer.py` — `AudioWriter` (opcional)
- **`AudioWriter.__init__(path, sample_rate=16000)`**.
- **`start()`** — Abre WAV mono int16, sobe thread daemon.
- **`append(audio)`** — Enfileira chunk float32; thread quantiza pra int16 e grava.
- **`close()`** — Poison pill, join, fecha WAV.

### `meeting/intelligence/types.py`
- **`SuggestionKind`** — Enum `PERSONAL | TECHNICAL | HYBRID`.
- **`Suggestion`** — Dataclass `(kind, text, source_turn_id, used_chunks)`.

### `meeting/intelligence/question_detector.py`
- **`QuestionDetector.__init__(prosody_ratio=1.3)`**.
- **`is_question(text, audio_tail)`** [meeting/intelligence/question_detector.py:30] — 2-de-3 sinais: termina com `?`, contém palavra-chave interrogativa (`como`, `qual`, `por que`, `me conta`, etc), prosódia subindo (energia RMS do fim > 1.3× início).

### `meeting/intelligence/classifier.py`
- **`Classifier.__init__(llm, model)`**.
- **`classify(question, context)`** [meeting/intelligence/classifier.py:24] — Chama LLM rápido (Llama 8B Instant) com prompt single-token A/B/C. Retorna `SuggestionKind`. Erro → HYBRID (fallback seguro).

### `meeting/intelligence/llm_client.py`
- **`LlmConfig`** — Dataclass `(provider, model, api_key_env, temperature, max_tokens, local_*)`.
- **`LlmMessage`** — Dataclass `(role, content)`.
- **`LlmClient.complete(messages)`** [meeting/intelligence/llm_client.py:36] — Dispatcher por provider.
- **`_complete_groq(messages)`** — Lazy-init `groq.Groq(api_key=env)`. Chama `chat.completions.create`. Erro de key ausente → `RuntimeError` explícito.
- **`_complete_local(messages)`** — Lazy-init `llama_cpp.Llama` com GGUF Qwen. Prompt em formato `<|im_start|>...` chat-template.

### `meeting/intelligence/rag/chunker.py`
- **`chunk_text(text, chunk_size=500, overlap=50)`** — Split por **palavras**. Tail menor que `step` é descartado (já coberto pelo overlap do anterior).

### `meeting/intelligence/rag/indexer.py`
- **`IndexedChunk`** — Dataclass `(text, source, embedding)`.
- **`RagIndexer.__init__(knowledge_dir, embedder, chunk_size, overlap)`**.
- **`build_or_load(force=False)`** [meeting/intelligence/rag/indexer.py:79] — Hash de filenames+sizes+mtimes vira signature. Se `.index.npz` existe com mesma signature, carrega do disco. Senão lê `.md`/`.txt`/`.pdf`, chunka, embedda, salva. PDF: `pypdf.PdfReader` com try/except.
- **`_signature()`** — SHA-256.
- **`_iter_files()`** — Walk recursivo, filtra extensão e arquivos ocultos.
- **`matrix()`** — Stack de embeddings.

### `meeting/intelligence/rag/retriever.py`
- **`RagRetriever.__init__(chunks, embedder)`** — Stack pré-computado.
- **`retrieve(query, top_k=5)`** [meeting/intelligence/rag/retriever.py:21] — Embedda query, dot product (=cosine pois normalizado), argsort, top-k. Vazio → `[]`.

### `meeting/intelligence/responder.py`
- **`Responder.__init__(retriever, classifier, llm, model, top_k, system_prompts)`**.
- **`respond(question, recent_context)`** [meeting/intelligence/responder.py:46] — Classifica → recupera (se PERSONAL/HYBRID) → monta system+user prompt → LLM → `Suggestion`.

### `meeting/intelligence/summarizer.py`
- **`Summarizer.__init__(llm, model)`**.
- **`summarize(turns)`** [meeting/intelligence/summarizer.py:18] — Concatena todas as linhas, manda pro LLM com prompt pedindo seções `## Resumo / ## Tópicos / ## Decisões / ## Action items`. Sem turnos → fallback fixo. Erro do LLM → markdown com mensagem de erro (não quebra).

### `meeting/ui/invisibility.py`
- **`set_window_invisible_to_capture(hwnd, enabled)`** [meeting/ui/invisibility.py:15] — `user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE=0x11)`. Faz a janela sumir em Teams/Zoom/OBS/screen-share. `False` remove. Windows 10 2004+/11.

### `meeting/ui/suggestion_card.py`
- **`SuggestionCard(QFrame)`** — Card colorido por `SuggestionKind` (amarelo/azul/roxo). Botões `✓ Usar` (emite `use_clicked(text)`) e `✕` (emite `dismiss_clicked`).

### `meeting/ui/transcript_view.py`
- **`TranscriptView(QTextEdit)`** — Read-only. Cores por speaker (verde `[Você]`, azul `[Eles]`).
- **`append_turn(turn)`** — Adiciona linha HTML. Auto-scroll para o fim **a menos que** o usuário tenha scrollado pra cima manualmente.

### `meeting/ui/live_window.py`
- **`LiveWindow.__init__(opacity=0.92)`** — Cria QWidget sempre-no-topo, monta layout (header + suggestion_holder + transcript + bottom). Restaura geometria de `.window_state.json`. Aplica invisibility via `QTimer.singleShot(0, ...)` depois que `winId()` é válido.
- **`append_turn(turn)`** — Repassa pro `TranscriptView`.
- **`show_suggestion(suggestion, ttl_seconds)`** [meeting/ui/live_window.py:81] — Remove card atual, cria novo, conecta sinais, dispara timer pra auto-dismiss.
- **`_copy_to_clipboard(text)`** — `QApplication.clipboard().setText(text)`, dismiss.
- **`_apply_invisibility()`** — Chama o helper de `meeting/ui/invisibility.py`.
- **`closeEvent`** — Salva geometria em `meeting/.window_state.json`.
- **Shortcuts:** `Esc` dismiss, `Enter` use, `Ctrl+P` pause, `Ctrl+Q` stop.

### `meeting/controller.py` — Orquestrador do modo reunião
- **`MeetingDeps`** — Dataclass agrupando todas dependências injetadas (testabilidade).
- **`MeetingController.__init__(deps)`** — Cria 2 `Vad` + 2 `ChannelBuffer` (`_buf_them` `_buf_you`), inicializa `_turns=[]`, `_recent_them_audio=deque(maxlen=10)`.
- **`start()`** [meeting/controller.py:55] — Cria SessionWriter via factory, inicia. Sobe pipeline. Conecta `on_audio` dos capturers em `_on_mic_audio`/`_on_sys_audio`. Abre capturers. Estado → RECORDING.
- **`stop()`** [meeting/controller.py:71] — Sequência exata (todos try/except: nenhum erro impede o resto):
  1. `mic_capture.close()`
  2. `system_capture.close()`
  3. `_buf_them.on_turn_end()` — flush
  4. `_buf_you.on_turn_end()` — flush
  5. `pipeline.stop()` — drena fila + shutdown pool
  6. `summarizer.summarize(self._turns)` — chama LLM
  7. `writer.finalize(summary=...)` — grava `sumario.md`
  8. Estado → STOPPED.
- **`_on_mic_audio(chunk)`** — Alimenta `_buf_you` e `_vad_you`; on turn_end → flush buffer.
- **`_on_sys_audio(chunk)`** — Mesmo pra `_buf_them` + `_vad_them` + guarda os últimos chunks em `_recent_them_audio` (pra prosódia).
- **`_on_chunk(speaker, audio)`** — Submetida ao pipeline.
- **`_on_turn(turn)`** [meeting/controller.py:130] — Append em `_turns`, `writer.append_turn`, `live_window.append_turn`. Se `THEM` + `question_detection`: monta `tail` (concat dos chunks recentes), `question_detector.is_question(text, tail)`. Se sim e `auto_suggest`: thread roda `_respond_async`.
- **`_respond_async(turn)`** [meeting/controller.py:151] — Constrói `recent_context` (últimos N minutos de transcrição), chama `responder.respond`, `live_window.show_suggestion`.
- **`_recent_context()`** — Filtra `_turns` por `wall_clock >= now - context_window_minutes*60`.

---

## Configs

### `config.yaml` (ditado, raiz)
- `whisper.model` — `small` por padrão (vs `tiny|base|medium|large-v3`).
- `whisper.language` — `pt`.
- `whisper.device` / `compute_type` — `auto`.
- `whisper.beam_size` — 5.
- `audio.prebuffer_seconds` — 0.6 (pré-buffer rolling do ditado).
- `hotkey.combo` — `ctrl+win`.
- `inject.restore_clipboard` — true.

### `meeting/meeting_config.yaml`
- `audio.system_loopback` / `microphone` — toggles dos canais.
- `audio.vad_silence_ms` — 800.
- `audio.save_raw_wav` — false (default).
- `transcribe.model` — `small`.
- `transcribe.parallel_workers` — 2.
- `llm.provider` — `groq` (alternativas: `local`, `anthropic`, `openai`).
- `llm.model` — `llama-3.3-70b-versatile`.
- `llm.classifier_model` — `llama-3.1-8b-instant`.
- `llm.api_key_env` — `GROQ_API_KEY`.
- `rag.knowledge_dir` — `knowledge`.
- `rag.embedding_model` — `paraphrase-multilingual-MiniLM-L12-v2`.
- `rag.chunk_size` / `chunk_overlap` / `top_k` — 500 / 50 / 5.
- `intelligence.context_window_minutes` — 2.
- `intelligence.suggestion_ttl_seconds` — 90.
- `intelligence.auto_suggest` / `question_detection` — true.
- `ui.invisible_to_capture` / `always_on_top` / `opacity` — true/true/0.92.
- `storage.output_dir` — `reunioes`.

## Artefatos em disco

- `models/` — modelos Whisper (download HuggingFace, ~500MB pra `small`).
- `knowledge/` — markdown/PDF do usuário. `.index.npz` é cache de embeddings (gitignored).
- `reunioes/<YYYY-MM-DD_HH-MM>/` — `transcript.txt`, `sumario.md`, opcional `audio.wav`.
- `meeting/.window_state.json` — geometria persistida da `LiveWindow`.
- `sussurro.log` — log rotativo ao lado do exe.

## Build do exe

- `Sussurro.spec` — config PyInstaller. Inclui `meeting/meeting_config.yaml`, hidden imports de sentence_transformers/silero_vad/groq/pyaudiowpatch/etc.
- `scripts/finalize_dist.py` — pós-build: copia `config.yaml` + `models/` pra `dist/Sussurro/`.
- Comando: `python -m PyInstaller Sussurro.spec --noconfirm && python scripts/finalize_dist.py`.

## Tests

- `tests/meeting/test_*.py` — 43 testes cobrindo cada peça (VAD, capturers via fakes, pipeline, RAG, classifier, responder, controller). `pytest tests/meeting/ -v`.
