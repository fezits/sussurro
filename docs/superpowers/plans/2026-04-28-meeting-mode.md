# Sussurro Meeting Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a meeting mode that captures Teams/Meet/Zoom audio (system loopback + mic), transcribes both channels live, shows an always-on-top window invisible to screen capture, and suggests answers to detected questions using a personal RAG knowledge base + Groq Llama 3.3 70B.

**Architecture:** New `meeting/` package coexisting with existing `src/` (dictation) and `server/` (mobile). State machine in `MeetingController` orchestrates dual capture pipelines, a transcription worker pool, an intelligence pipeline (question detection → classification → RAG → LLM), and a Qt live window with `WDA_EXCLUDEFROMCAPTURE`. Default LLM provider is Groq's free tier; Qwen 2.5 7B GGUF local fallback is opt-in.

**Tech Stack:** Python 3.14, PySide6 (Qt), `pyaudiowpatch` (WASAPI loopback), `sounddevice` (mic), `silero-vad` (VAD ONNX), `faster-whisper` (transcription, model `small` already on disk), `sentence-transformers` (embeddings, multilingual), `groq` SDK (default LLM), `pypdf` (knowledge ingestion), `llama-cpp-python` (local LLM, opt-in), `pywin32` (`SetWindowDisplayAffinity`).

---

## Reading order

Tasks are grouped into **phases** that build on each other. Within a phase, tasks must be completed in order. Phases:

1. **Foundation** — config, types, dependencies, knowledge folder scaffold (Tasks 1-3)
2. **Audio capture** — VAD + dual capture (Tasks 4-7)
3. **Transcription pipeline** — workers + turns (Tasks 8-10)
4. **Persistence** — autosave + final artifacts (Tasks 11-12)
5. **Intelligence** — RAG indexer/retriever, LLM client, classifier, responder, summarizer (Tasks 13-19)
6. **UI** — invisibility helper, suggestion card, transcript view, live window (Tasks 20-24)
7. **Controller + integration** — state machine wiring everything, integrate with existing bubble menu (Tasks 25-27)
8. **Build + e2e** — spec update, smoke test, README (Tasks 28-30)

Each task: TDD where applicable (logic), pragmatic for IO/UI/audio (write code + manual smoke test). Commit after every task.

---

## Phase 1 — Foundation

### Task 1: Project scaffold for `meeting/` package

**Files:**
- Create: `meeting/__init__.py`
- Create: `meeting/meeting_config.yaml`
- Create: `meeting/audio/__init__.py`
- Create: `meeting/transcribe/__init__.py`
- Create: `meeting/intelligence/__init__.py`
- Create: `meeting/intelligence/rag/__init__.py`
- Create: `meeting/persistence/__init__.py`
- Create: `meeting/ui/__init__.py`
- Create: `knowledge/.gitkeep`
- Create: `knowledge/perfil.md` (template)
- Modify: `.gitignore`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p meeting/audio meeting/transcribe meeting/intelligence/rag meeting/persistence meeting/ui knowledge/projetos knowledge/tecnico knowledge/entrevistas reunioes
```

Then create each `__init__.py` as an empty file via Write tool:

```python
# meeting/__init__.py and all sub-package __init__.py files
```

- [ ] **Step 2: Write default `meeting/meeting_config.yaml`**

```yaml
audio:
  system_loopback: true
  microphone: true
  save_raw_wav: false
  vad_silence_ms: 800

transcribe:
  model: small
  language: pt
  parallel_workers: 2

llm:
  provider: groq                # groq | local | anthropic | openai
  model: llama-3.3-70b-versatile
  api_key_env: GROQ_API_KEY
  classifier_model: llama-3.1-8b-instant

  local:
    model_path: models/llm/qwen2.5-7b-instruct-q4_k_m.gguf
    n_ctx: 8192
    n_threads: 8

rag:
  knowledge_dir: knowledge
  embedding_model: paraphrase-multilingual-MiniLM-L12-v2
  chunk_size: 500
  chunk_overlap: 50
  top_k: 5

intelligence:
  question_detection: true
  auto_suggest: true
  context_window_minutes: 2
  suggestion_ttl_seconds: 90

ui:
  invisible_to_capture: true
  opacity: 0.92
  always_on_top: true

storage:
  output_dir: reunioes
```

- [ ] **Step 3: Write `knowledge/perfil.md` template**

```markdown
# Perfil — Fernando Braidatto

Edite este arquivo livre com tudo sobre você. O Sussurro vai usar como contexto pra responder perguntas pessoais em entrevistas/reuniões. Frases em primeira pessoa funcionam melhor — o LLM imita o tom.

## Bio curta

(Quem é você em 2-3 frases. Ex: "Sou desenvolvedor com 12 anos de experiência, focado em backend e dados. Atualmente em SuperaHoldings...")

## Experiência profissional

(Empresas, períodos, responsabilidades, principais entregas)

## Skills técnicas

(Linguagens, frameworks, ferramentas — agrupados por área)

## Projetos relevantes

(O que você fez, qual o desafio, como resolveu)

## Valores e estilo de trabalho

(Como você gosta de trabalhar, o que valoriza, exemplos de situações)

## Frases típicas suas

(Palavras/expressões que você usa muito — ajuda o LLM a imitar seu tom)
```

- [ ] **Step 4: Add new entries to `.gitignore`**

Append these lines to `.gitignore`:

```
# Meeting mode
reunioes/
knowledge/.index.npz
knowledge/.partial/
meeting/.window_state.json

# LLM models (downloaded on demand)
models/llm/
```

- [ ] **Step 5: Commit**

```bash
git add meeting/ knowledge/ reunioes/.gitkeep .gitignore
git commit -m "feat(meeting): scaffold package, default config, knowledge template"
```

---

### Task 2: Add new dependencies to `requirements.txt`

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append new dependencies**

Add these lines at the end of `requirements.txt`:

```
# Meeting mode
pyaudiowpatch>=0.2.12
silero-vad>=5.1
sentence-transformers>=3.0
groq>=0.13
pypdf>=5.0
pywin32>=308
# Optional/opt-in (uncomment if needed)
# llama-cpp-python>=0.3
# anthropic>=0.40
# openai>=1.50
```

- [ ] **Step 2: Install everything**

Run: `pip install -r requirements.txt`
Expected: all install OK. If any fail on Python 3.14, note the failure but continue (`llama-cpp-python` is opt-in).

- [ ] **Step 3: Validate imports**

Run:
```bash
python -c "import pyaudiowpatch, sentence_transformers, groq, pypdf, win32api; print('IMPORTS OK')"
```
Expected: `IMPORTS OK`. If `silero-vad` import fails (it ships as PyPI `silero-vad` but imports as `silero_vad`), test instead:
```bash
python -c "from silero_vad import load_silero_vad; print('VAD OK')"
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(meeting): add audio capture, RAG and LLM deps"
```

---

### Task 3: Define core dataclasses (`Turn`, `Suggestion`, `MeetingState`)

**Files:**
- Create: `meeting/transcribe/turn.py`
- Create: `meeting/intelligence/types.py`
- Create: `meeting/state.py`
- Test: `tests/meeting/test_types.py`

- [ ] **Step 1: Create test directory and write the failing test**

```bash
mkdir -p tests/meeting
```

Write `tests/meeting/__init__.py` (empty file).

Write `tests/meeting/test_types.py`:

```python
from datetime import datetime
from meeting.transcribe.turn import Turn, Speaker
from meeting.intelligence.types import Suggestion, SuggestionKind
from meeting.state import MeetingState, SessionId


def test_turn_to_line_formats_with_timestamp():
    t = Turn(
        speaker=Speaker.YOU,
        start=12.0,
        end=15.0,
        text="ola pessoal",
        wall_clock=datetime(2026, 4, 28, 14, 32, 1),
    )
    assert t.to_line() == "14:32:01 [Você]   ola pessoal"


def test_turn_to_line_them_speaker_aligns():
    t = Turn(
        speaker=Speaker.THEM,
        start=0.0,
        end=2.0,
        text="oi",
        wall_clock=datetime(2026, 4, 28, 14, 32, 1),
    )
    assert "[Eles]" in t.to_line()


def test_suggestion_has_kind_and_text():
    s = Suggestion(kind=SuggestionKind.PERSONAL, text="abc", source_turn_id="t1")
    assert s.kind is SuggestionKind.PERSONAL
    assert s.text == "abc"


def test_session_id_is_filesystem_safe():
    sid = SessionId.now(datetime(2026, 4, 28, 14, 32))
    assert sid.value == "2026-04-28_14-32"


def test_meeting_state_transitions():
    ms = MeetingState.IDLE
    assert ms is not MeetingState.RECORDING
    assert MeetingState("recording") is MeetingState.RECORDING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meeting/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `meeting/transcribe/turn.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Speaker(str, Enum):
    YOU = "Você"
    THEM = "Eles"


@dataclass(frozen=True)
class Turn:
    speaker: Speaker
    start: float          # seconds since meeting start
    end: float
    text: str
    wall_clock: datetime  # absolute timestamp (used for the rendered line)

    def to_line(self) -> str:
        """One-line rendering used by transcript.txt and the live view."""
        ts = self.wall_clock.strftime("%H:%M:%S")
        speaker_box = f"[{self.speaker.value}]"
        # 8 chars covers both "[Eles]" (6) and "[Você]" (6) plus padding.
        padded = speaker_box.ljust(8)
        return f"{ts} {padded} {self.text}"
```

- [ ] **Step 4: Write `meeting/intelligence/types.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SuggestionKind(str, Enum):
    PERSONAL = "personal"     # 🧠 amarelo
    TECHNICAL = "technical"   # 📚 azul
    HYBRID = "hybrid"         # 🔀 roxo


@dataclass(frozen=True)
class Suggestion:
    kind: SuggestionKind
    text: str
    source_turn_id: str
    used_chunks: tuple[str, ...] = ()  # rag chunks that fed the prompt
```

- [ ] **Step 5: Write `meeting/state.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MeetingState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True)
class SessionId:
    value: str

    @classmethod
    def now(cls, when: datetime | None = None) -> "SessionId":
        when = when or datetime.now()
        return cls(when.strftime("%Y-%m-%d_%H-%M"))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/meeting/test_types.py -v`
Expected: 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add meeting/transcribe/turn.py meeting/intelligence/types.py meeting/state.py tests/meeting/
git commit -m "feat(meeting): core dataclasses Turn, Suggestion, MeetingState"
```

---

## Phase 2 — Audio capture

### Task 4: VAD wrapper around silero-vad

**Files:**
- Create: `meeting/audio/vad.py`
- Test: `tests/meeting/test_vad.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np

from meeting.audio.vad import Vad


def test_vad_emits_turn_end_on_silence():
    vad = Vad(silence_ms=400, sample_rate=16000)

    # 2 seconds of "speech" then 0.5s of silence
    speech = (np.random.randn(2 * 16000) * 0.4).astype(np.float32)
    silence = np.zeros(int(0.5 * 16000), dtype=np.float32)

    events: list[str] = []
    for chunk in np.array_split(speech, 20):
        for e in vad.feed(chunk):
            events.append(e)
    for chunk in np.array_split(silence, 5):
        for e in vad.feed(chunk):
            events.append(e)

    assert "turn_end" in events


def test_vad_no_event_for_pure_silence():
    vad = Vad(silence_ms=400, sample_rate=16000)
    silence = np.zeros(16000, dtype=np.float32)
    events = list(vad.feed(silence))
    assert events == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meeting/test_vad.py -v`
Expected: FAIL `ModuleNotFoundError: meeting.audio.vad`.

- [ ] **Step 3: Implement `meeting/audio/vad.py`**

```python
from __future__ import annotations

from collections.abc import Iterator

import numpy as np
from silero_vad import load_silero_vad


class Vad:
    """Streaming VAD that emits 'turn_end' events after `silence_ms` of silence
    following at least one chunk of detected speech.

    Uses silero-vad in 32ms (512-sample) frames at 16kHz. Stateless across
    instances, but tracks 'speaking' state internally so that 'turn_end' fires
    once per turn.
    """

    FRAME = 512  # 32ms @ 16kHz, the only size silero-vad supports

    def __init__(self, silence_ms: int = 800, sample_rate: int = 16000) -> None:
        if sample_rate != 16000:
            raise ValueError("Vad only supports 16kHz")
        self.model = load_silero_vad()
        self.silence_frames_threshold = max(1, silence_ms // 32)
        self.sample_rate = sample_rate

        self._buf = np.zeros(0, dtype=np.float32)
        self._was_speaking = False
        self._silent_frames = 0

    def feed(self, audio: np.ndarray) -> Iterator[str]:
        """Feed a mono float32 chunk; yields 'turn_end' when a turn closes."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        self._buf = np.concatenate([self._buf, audio])

        while len(self._buf) >= self.FRAME:
            frame = self._buf[: self.FRAME]
            self._buf = self._buf[self.FRAME :]

            import torch
            prob = float(self.model(torch.from_numpy(frame), self.sample_rate).item())
            speech = prob >= 0.5

            if speech:
                self._was_speaking = True
                self._silent_frames = 0
            else:
                if self._was_speaking:
                    self._silent_frames += 1
                    if self._silent_frames >= self.silence_frames_threshold:
                        self._was_speaking = False
                        self._silent_frames = 0
                        yield "turn_end"

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.float32)
        self._was_speaking = False
        self._silent_frames = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meeting/test_vad.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/audio/vad.py tests/meeting/test_vad.py
git commit -m "feat(meeting): VAD wrapper with turn_end events"
```

---

### Task 5: `MicCapture` (continuous mic stream sharable with dictation)

**Files:**
- Create: `meeting/audio/mic_capture.py`
- Test: `tests/meeting/test_mic_capture.py`

- [ ] **Step 1: Write the failing test (uses fakes; no real mic)**

```python
import threading
import time

import numpy as np

from meeting.audio.mic_capture import MicCapture


class _FakeStream:
    """Mimics sounddevice.InputStream: invokes callback in a thread until close."""

    def __init__(self, callback, samplerate, channels, dtype, blocksize, **_kw):
        self.callback = callback
        self.samplerate = samplerate
        self.blocksize = blocksize or 1024
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True

        def _loop():
            while self._running:
                buf = (np.random.randn(self.blocksize, 1) * 0.1).astype(np.float32)
                self.callback(buf, self.blocksize, None, None)
                time.sleep(self.blocksize / self.samplerate)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def close(self) -> None:
        self.stop()


def test_mic_capture_collects_samples(monkeypatch):
    import meeting.audio.mic_capture as mod
    monkeypatch.setattr(mod.sd, "InputStream", _FakeStream)

    received: list[np.ndarray] = []
    cap = MicCapture(sample_rate=16000, on_audio=lambda chunk: received.append(chunk))
    cap.open()
    time.sleep(0.3)
    cap.close()

    assert len(received) > 0
    total = sum(c.size for c in received)
    assert total > 0
    assert all(c.dtype == np.float32 for c in received)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meeting/test_mic_capture.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `meeting/audio/mic_capture.py`**

```python
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import sounddevice as sd


class MicCapture:
    """Continuous mic capture. Calls `on_audio` with mono float32 chunks at 16kHz.

    Designed to coexist with src/recorder.py from dictation: both can open the
    default input device simultaneously on Windows (WASAPI shared mode).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        blocksize: int = 0,
        on_audio: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.on_audio = on_audio or (lambda _c: None)
        self._stream: sd.InputStream | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata[:, 0] if indata.ndim > 1 else indata.reshape(-1)
        chunk = np.ascontiguousarray(mono, dtype=np.float32).copy()
        self.on_audio(chunk)

    def open(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()

    def close(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meeting/test_mic_capture.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/audio/mic_capture.py tests/meeting/test_mic_capture.py
git commit -m "feat(meeting): continuous mic capture for meeting mode"
```

---

### Task 6: `SystemCapture` (WASAPI loopback for "Eles")

**Files:**
- Create: `meeting/audio/system_capture.py`
- Test: `tests/meeting/test_system_capture.py`

- [ ] **Step 1: Write the failing test (with fake)**

```python
import threading
import time

import numpy as np

from meeting.audio.system_capture import SystemCapture


class _FakePyAudio:
    """Mimics pyaudiowpatch enough for SystemCapture."""

    paFloat32 = 1
    paContinue = 0

    def __init__(self) -> None:
        self.opened: list[dict] = []

    def get_default_wasapi_loopback(self):
        return {
            "index": 1,
            "name": "Speakers (Loopback)",
            "defaultSampleRate": 48000,
            "maxInputChannels": 2,
        }

    def open(self, **kwargs):
        self.opened.append(kwargs)
        return _FakeStream(kwargs)

    def terminate(self):
        pass


class _FakeStream:
    def __init__(self, kwargs):
        self.callback = kwargs["stream_callback"]
        self.frames = kwargs.get("frames_per_buffer", 1024)
        self.rate = kwargs.get("rate", 48000)
        self.channels = kwargs.get("channels", 2)
        self._running = False
        self._t: threading.Thread | None = None

    def start_stream(self):
        self._running = True
        def _loop():
            while self._running:
                samples = (np.random.randn(self.frames, self.channels) * 0.05).astype(np.float32)
                self.callback(samples.tobytes(), self.frames, None, 0)
                time.sleep(self.frames / self.rate)
        self._t = threading.Thread(target=_loop, daemon=True)
        self._t.start()

    def stop_stream(self):
        self._running = False
        if self._t: self._t.join(timeout=1)

    def close(self):
        self.stop_stream()


def test_system_capture_resamples_and_downmixes(monkeypatch):
    import meeting.audio.system_capture as mod
    monkeypatch.setattr(mod, "_PyAudio", _FakePyAudio)

    received: list[np.ndarray] = []
    cap = SystemCapture(target_rate=16000, on_audio=lambda c: received.append(c))
    cap.open()
    time.sleep(0.3)
    cap.close()

    assert len(received) > 0
    for c in received:
        assert c.ndim == 1
        assert c.dtype == np.float32
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meeting/test_system_capture.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `meeting/audio/system_capture.py`**

```python
from __future__ import annotations

from collections.abc import Callable

import numpy as np

try:
    import pyaudiowpatch as _PyAudioModule
    _PyAudio = _PyAudioModule.PyAudio
except ImportError:  # tests inject a fake
    _PyAudio = None  # type: ignore


class SystemCapture:
    """Captures everything coming out of the speakers via WASAPI loopback.

    Resamples to `target_rate` mono float32 in the audio callback so consumers
    see the same shape MicCapture provides.
    """

    def __init__(
        self,
        target_rate: int = 16000,
        on_audio: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        if _PyAudio is None:
            raise RuntimeError("pyaudiowpatch not available")
        self.target_rate = target_rate
        self.on_audio = on_audio or (lambda _c: None)
        self._pa = _PyAudio()
        self._stream = None
        self._device_rate = 48000
        self._device_channels = 2

    def _callback(self, in_data, frame_count, time_info, status):
        raw = np.frombuffer(in_data, dtype=np.float32)
        if self._device_channels == 2 and raw.size >= 2:
            raw = raw.reshape(-1, 2).mean(axis=1)
        if self._device_rate != self.target_rate and raw.size > 0:
            ratio = self.target_rate / self._device_rate
            new_len = max(1, int(round(raw.size * ratio)))
            x_old = np.linspace(0.0, 1.0, num=raw.size, endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
            raw = np.interp(x_new, x_old, raw).astype(np.float32)
        self.on_audio(np.ascontiguousarray(raw, dtype=np.float32))
        return (None, 0)  # paContinue

    def open(self) -> None:
        if self._stream is not None:
            return
        info = self._pa.get_default_wasapi_loopback()
        self._device_rate = int(info["defaultSampleRate"])
        self._device_channels = int(info.get("maxInputChannels", 2)) or 2
        self._stream = self._pa.open(
            format=getattr(self._pa, "paFloat32", 1),
            channels=self._device_channels,
            rate=self._device_rate,
            input=True,
            input_device_index=info["index"],
            frames_per_buffer=1024,
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            finally:
                self._stream = None
        try:
            self._pa.terminate()
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meeting/test_system_capture.py -v`
Expected: PASS.

- [ ] **Step 5: Manual smoke test (optional but recommended)**

Run on Windows with a YouTube video playing:

```bash
python -c "
import time
from meeting.audio.system_capture import SystemCapture
total = []
cap = SystemCapture(on_audio=lambda c: total.append(c.size))
cap.open()
time.sleep(2)
cap.close()
print(f'samples: {sum(total)}')
"
```
Expected: samples > 30000 (2s @ 16kHz). If 0, the loopback device wasn't available; document the failure and continue.

- [ ] **Step 6: Commit**

```bash
git add meeting/audio/system_capture.py tests/meeting/test_system_capture.py
git commit -m "feat(meeting): WASAPI loopback capture for system audio"
```

---

### Task 7: `ChannelBuffer` — accumulates audio + cuts on VAD events

**Files:**
- Create: `meeting/audio/channel_buffer.py`
- Test: `tests/meeting/test_channel_buffer.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np

from meeting.audio.channel_buffer import ChannelBuffer
from meeting.transcribe.turn import Speaker


def test_buffer_emits_chunk_on_turn_end():
    chunks: list[tuple[Speaker, np.ndarray]] = []
    buf = ChannelBuffer(
        speaker=Speaker.YOU,
        on_chunk=lambda speaker, audio: chunks.append((speaker, audio)),
        max_seconds=30.0,
    )

    audio = (np.random.randn(16000 * 2) * 0.3).astype(np.float32)
    buf.feed_audio(audio)
    buf.on_turn_end()

    assert len(chunks) == 1
    assert chunks[0][0] is Speaker.YOU
    assert chunks[0][1].size == 16000 * 2


def test_buffer_force_flushes_when_too_long():
    chunks: list[tuple[Speaker, np.ndarray]] = []
    buf = ChannelBuffer(
        speaker=Speaker.THEM,
        on_chunk=lambda s, a: chunks.append((s, a)),
        max_seconds=1.0,
    )
    buf.feed_audio(np.zeros(16000, dtype=np.float32))   # 1s
    buf.feed_audio(np.zeros(16000, dtype=np.float32))   # 2s -> auto-flush
    assert len(chunks) >= 1


def test_buffer_drops_empty_turn():
    chunks: list = []
    buf = ChannelBuffer(Speaker.YOU, on_chunk=lambda s, a: chunks.append((s, a)))
    buf.on_turn_end()
    assert chunks == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meeting/test_channel_buffer.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `meeting/audio/channel_buffer.py`**

```python
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from meeting.transcribe.turn import Speaker


class ChannelBuffer:
    """Per-channel buffer that accumulates audio and emits a chunk:
       1. when an external `on_turn_end()` is called, OR
       2. when accumulated audio exceeds `max_seconds`.
    Empty buffers (no audio since last flush) emit nothing.
    """

    def __init__(
        self,
        speaker: Speaker,
        on_chunk: Callable[[Speaker, np.ndarray], None],
        sample_rate: int = 16000,
        max_seconds: float = 30.0,
    ) -> None:
        self.speaker = speaker
        self.on_chunk = on_chunk
        self.sample_rate = sample_rate
        self.max_samples = int(max_seconds * sample_rate)
        self._parts: list[np.ndarray] = []
        self._size = 0

    def feed_audio(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        self._parts.append(audio)
        self._size += audio.size
        if self._size >= self.max_samples:
            self._flush()

    def on_turn_end(self) -> None:
        self._flush()

    def _flush(self) -> None:
        if self._size == 0:
            return
        audio = np.concatenate(self._parts).astype(np.float32)
        self._parts.clear()
        self._size = 0
        self.on_chunk(self.speaker, audio)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meeting/test_channel_buffer.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/audio/channel_buffer.py tests/meeting/test_channel_buffer.py
git commit -m "feat(meeting): channel buffer with VAD-driven and overflow flush"
```

---

## Phase 3 — Transcription pipeline

### Task 8: `TranscribePipeline` worker pool

**Files:**
- Create: `meeting/transcribe/pipeline.py`
- Test: `tests/meeting/test_pipeline.py`

- [ ] **Step 1: Write the failing test using a fake transcriber**

```python
import time
from datetime import datetime

import numpy as np

from meeting.transcribe.pipeline import TranscribePipeline
from meeting.transcribe.turn import Speaker, Turn


class _FakeTranscriber:
    def transcribe(self, audio: np.ndarray) -> str:
        # Echo the audio length so tests can assert ordering.
        return f"audio_{audio.size}"


def test_pipeline_produces_turns_in_order():
    received: list[Turn] = []
    pipe = TranscribePipeline(
        transcriber=_FakeTranscriber(),
        workers=2,
        on_turn=received.append,
        meeting_start=datetime(2026, 4, 28, 14, 0, 0),
    )
    pipe.start()
    pipe.submit(Speaker.YOU, np.ones(16000, dtype=np.float32))
    pipe.submit(Speaker.THEM, np.ones(8000, dtype=np.float32))

    deadline = time.time() + 3
    while len(received) < 2 and time.time() < deadline:
        time.sleep(0.05)
    pipe.stop()

    assert len(received) == 2
    assert {t.speaker for t in received} == {Speaker.YOU, Speaker.THEM}
    for t in received:
        assert t.text.startswith("audio_")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meeting/test_pipeline.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `meeting/transcribe/pipeline.py`**

```python
from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Queue
from typing import Protocol

import numpy as np

from meeting.transcribe.turn import Speaker, Turn


class _Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...


class TranscribePipeline:
    """Submits (speaker, audio) jobs and emits Turn objects via on_turn."""

    def __init__(
        self,
        transcriber: _Transcriber,
        on_turn: Callable[[Turn], None],
        workers: int = 2,
        sample_rate: int = 16000,
        meeting_start: datetime | None = None,
    ) -> None:
        self.transcriber = transcriber
        self.on_turn = on_turn
        self.workers = workers
        self.sample_rate = sample_rate
        self.meeting_start = meeting_start or datetime.now()
        self._pool: ThreadPoolExecutor | None = None
        self._queue: Queue = Queue()
        self._running = False
        self._dispatcher: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="transcribe")
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)  # poison pill
        if self._dispatcher:
            self._dispatcher.join(timeout=2)
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=False)
        self._pool = None

    def submit(self, speaker: Speaker, audio: np.ndarray) -> None:
        if not self._running or audio.size == 0:
            return
        wall = datetime.now()
        self._queue.put((speaker, audio, wall))

    def _dispatch_loop(self) -> None:
        while self._running:
            item = self._queue.get()
            if item is None:
                return
            speaker, audio, wall = item
            assert self._pool is not None
            self._pool.submit(self._work, speaker, audio, wall)

    def _work(self, speaker: Speaker, audio: np.ndarray, wall: datetime) -> None:
        try:
            text = self.transcriber.transcribe(audio).strip()
        except Exception:
            return
        if not text:
            return
        duration = audio.size / self.sample_rate
        end_seconds = (wall - self.meeting_start).total_seconds()
        start_seconds = max(0.0, end_seconds - duration)
        turn = Turn(
            speaker=speaker,
            start=start_seconds,
            end=end_seconds,
            text=text,
            wall_clock=wall,
        )
        try:
            self.on_turn(turn)
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meeting/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/transcribe/pipeline.py tests/meeting/test_pipeline.py
git commit -m "feat(meeting): transcription worker pool emitting Turn objects"
```

---

### Task 9: `MeetingTranscriber` — adapter over `src/transcriber.py`

**Files:**
- Create: `meeting/transcribe/adapter.py`
- Test: `tests/meeting/test_adapter.py`

- [ ] **Step 1: Write a test using the fake from earlier**

```python
import numpy as np

from meeting.transcribe.adapter import MeetingTranscriber


class _StubInner:
    def transcribe(self, audio):
        return "  hello  "


def test_adapter_strips_and_returns_text(monkeypatch):
    adapter = MeetingTranscriber.__new__(MeetingTranscriber)
    adapter._inner = _StubInner()  # type: ignore[attr-defined]
    out = adapter.transcribe(np.zeros(16000, dtype=np.float32))
    assert out == "hello"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/meeting/test_adapter.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `meeting/transcribe/adapter.py`**

```python
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
```

- [ ] **Step 4: Run test**

Run: `pytest tests/meeting/test_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/transcribe/adapter.py tests/meeting/test_adapter.py
git commit -m "feat(meeting): MeetingTranscriber adapter over src.transcriber"
```

---

### Task 10: Integration test — capture → VAD → buffer → pipeline

**Files:**
- Test: `tests/meeting/test_capture_pipeline_integration.py`

- [ ] **Step 1: Write integration test (no real audio, deterministic)**

```python
import time
from datetime import datetime

import numpy as np

from meeting.audio.channel_buffer import ChannelBuffer
from meeting.audio.vad import Vad
from meeting.transcribe.pipeline import TranscribePipeline
from meeting.transcribe.turn import Speaker, Turn


class _FakeTranscriber:
    def transcribe(self, audio):
        return f"chunk_{audio.size}"


def test_full_path_speech_then_silence_creates_one_turn():
    received: list[Turn] = []
    pipe = TranscribePipeline(
        transcriber=_FakeTranscriber(),
        on_turn=received.append,
        workers=1,
        meeting_start=datetime.now(),
    )
    pipe.start()

    vad = Vad(silence_ms=400)
    buf = ChannelBuffer(
        speaker=Speaker.THEM,
        on_chunk=lambda s, a: pipe.submit(s, a),
        max_seconds=60.0,
    )

    speech = (np.random.randn(2 * 16000) * 0.4).astype(np.float32)
    silence = np.zeros(int(0.6 * 16000), dtype=np.float32)
    for chunk in np.array_split(speech, 20):
        buf.feed_audio(chunk)
        for ev in vad.feed(chunk):
            if ev == "turn_end":
                buf.on_turn_end()
    for chunk in np.array_split(silence, 5):
        buf.feed_audio(chunk)
        for ev in vad.feed(chunk):
            if ev == "turn_end":
                buf.on_turn_end()

    deadline = time.time() + 3
    while not received and time.time() < deadline:
        time.sleep(0.05)
    pipe.stop()

    assert len(received) == 1
    assert received[0].speaker is Speaker.THEM
    assert received[0].text.startswith("chunk_")
```

- [ ] **Step 2: Run**

Run: `pytest tests/meeting/test_capture_pipeline_integration.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/meeting/test_capture_pipeline_integration.py
git commit -m "test(meeting): integration test for capture-to-turn pipeline"
```

---

## Phase 4 — Persistence

### Task 11: `SessionWriter` — autosave + finalize

**Files:**
- Create: `meeting/persistence/session_writer.py`
- Test: `tests/meeting/test_session_writer.py`

- [ ] **Step 1: Failing test**

```python
from datetime import datetime
from pathlib import Path

from meeting.persistence.session_writer import SessionWriter
from meeting.state import SessionId
from meeting.transcribe.turn import Speaker, Turn


def test_writer_creates_session_dir_and_appends(tmp_path: Path):
    sid = SessionId.now(datetime(2026, 4, 28, 14, 30))
    sw = SessionWriter(root=tmp_path, session_id=sid)
    sw.start()

    sw.append_turn(Turn(Speaker.THEM, 0.0, 1.5, "ola", datetime(2026, 4, 28, 14, 30, 1)))
    sw.append_turn(Turn(Speaker.YOU, 1.5, 3.0, "oi tudo bem", datetime(2026, 4, 28, 14, 30, 2)))
    sw.flush_now()

    out = (tmp_path / "2026-04-28_14-30" / "transcript.txt").read_text(encoding="utf-8")
    assert "[Eles]" in out and "ola" in out
    assert "[Você]" in out and "oi tudo bem" in out


def test_writer_finalize_writes_summary(tmp_path: Path):
    sid = SessionId.now(datetime(2026, 4, 28, 14, 30))
    sw = SessionWriter(root=tmp_path, session_id=sid)
    sw.start()
    sw.append_turn(Turn(Speaker.THEM, 0, 1, "tema", datetime(2026, 4, 28, 14, 30, 1)))
    sw.finalize(summary="Reunião sobre tema X.")

    summary = (tmp_path / "2026-04-28_14-30" / "sumario.md").read_text(encoding="utf-8")
    assert "Reunião sobre tema X." in summary
```

- [ ] **Step 2: Run test**

Run: `pytest tests/meeting/test_session_writer.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `meeting/persistence/session_writer.py`**

```python
from __future__ import annotations

import threading
from pathlib import Path
from queue import Queue, Empty

from meeting.state import SessionId
from meeting.transcribe.turn import Turn


class SessionWriter:
    """Writes transcript.txt incrementally and produces the final sumario.md.

    Runs a daemon thread that drains a queue of Turn objects, appending one line
    each. flush_now() blocks until the queue is empty (used by tests and by
    explicit autosave triggers). finalize() stops the thread and writes the
    summary.
    """

    def __init__(self, root: Path | str, session_id: SessionId) -> None:
        self.root = Path(root)
        self.session_id = session_id
        self.dir = self.root / session_id.value
        self._queue: Queue[Turn | None] = Queue()
        self._thread: threading.Thread | None = None
        self._idle_event = threading.Event()
        self._idle_event.set()

    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        # Truncate transcript at start so re-runs of same session_id are clean.
        (self.dir / "transcript.txt").write_text("", encoding="utf-8")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def append_turn(self, turn: Turn) -> None:
        self._idle_event.clear()
        self._queue.put(turn)

    def flush_now(self, timeout: float = 5.0) -> None:
        self._idle_event.wait(timeout)

    def finalize(self, summary: str) -> None:
        self.flush_now()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
        (self.dir / "sumario.md").write_text(summary, encoding="utf-8")

    def _loop(self) -> None:
        path = self.dir / "transcript.txt"
        while True:
            try:
                turn = self._queue.get(timeout=0.5)
            except Empty:
                self._idle_event.set()
                continue
            if turn is None:
                self._idle_event.set()
                return
            with path.open("a", encoding="utf-8") as f:
                f.write(turn.to_line() + "\n")
            if self._queue.empty():
                self._idle_event.set()
```

- [ ] **Step 4: Run test**

Run: `pytest tests/meeting/test_session_writer.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/persistence/session_writer.py tests/meeting/test_session_writer.py
git commit -m "feat(meeting): session writer with autosave and finalize"
```

---

### Task 12: Optional raw audio writer

**Files:**
- Create: `meeting/persistence/audio_writer.py`
- Test: `tests/meeting/test_audio_writer.py`

- [ ] **Step 1: Failing test**

```python
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
```

- [ ] **Step 2: Run**

Run: `pytest tests/meeting/test_audio_writer.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `meeting/persistence/audio_writer.py`**

```python
from __future__ import annotations

import threading
import wave
from pathlib import Path
from queue import Queue

import numpy as np


class AudioWriter:
    """Optional WAV writer for the mixed (system + mic) meeting audio.
    Mono float32 input gets quantized to int16 for portability.
    """

    def __init__(self, path: Path | str, sample_rate: int = 16000) -> None:
        self.path = Path(path)
        self.sample_rate = sample_rate
        self._queue: Queue = Queue()
        self._thread: threading.Thread | None = None
        self._wav: wave.Wave_write | None = None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._wav = wave.open(str(self.path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(self.sample_rate)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def append(self, audio: np.ndarray) -> None:
        self._queue.put(audio.astype(np.float32))

    def close(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
        if self._wav is not None:
            self._wav.close()
            self._wav = None

    def _loop(self) -> None:
        assert self._wav is not None
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            pcm = np.clip(chunk * 32767.0, -32768, 32767).astype(np.int16)
            self._wav.writeframes(pcm.tobytes())
```

- [ ] **Step 4: Run**

Run: `pytest tests/meeting/test_audio_writer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/persistence/audio_writer.py tests/meeting/test_audio_writer.py
git commit -m "feat(meeting): optional raw audio writer for meetings"
```

---

## Phase 5 — Intelligence

### Task 13: RAG chunker

**Files:**
- Create: `meeting/intelligence/rag/chunker.py`
- Test: `tests/meeting/test_chunker.py`

- [ ] **Step 1: Failing test**

```python
from meeting.intelligence.rag.chunker import chunk_text


def test_chunker_returns_overlapping_chunks_close_to_size():
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    assert len(chunks) > 1
    assert all(50 <= len(c.split()) <= 110 for c in chunks)


def test_chunker_short_input_one_chunk():
    chunks = chunk_text("hello world", chunk_size=100, overlap=10)
    assert chunks == ["hello world"]
```

- [ ] **Step 2: Run**

Run: `pytest tests/meeting/test_chunker.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `meeting/intelligence/rag/chunker.py`**

```python
from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split into word-windowed chunks. chunk_size and overlap are in *words*."""
    words = text.split()
    if len(words) <= chunk_size:
        return [" ".join(words)] if words else []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    step = chunk_size - overlap
    chunks: list[str] = []
    i = 0
    while i < len(words):
        slice_ = words[i : i + chunk_size]
        if not slice_:
            break
        chunks.append(" ".join(slice_))
        i += step
    return chunks
```

- [ ] **Step 4: Run**

Run: `pytest tests/meeting/test_chunker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/intelligence/rag/chunker.py tests/meeting/test_chunker.py
git commit -m "feat(meeting): word-window text chunker for RAG"
```

---

### Task 14: RAG indexer (reads pasta `knowledge/`, gera embeddings)

**Files:**
- Create: `meeting/intelligence/rag/indexer.py`
- Test: `tests/meeting/test_indexer.py`

- [ ] **Step 1: Failing test (with stub embedder)**

```python
import json
from pathlib import Path

import numpy as np

from meeting.intelligence.rag.indexer import RagIndexer


class _StubEmbedder:
    """Deterministic 8-dim embedder: hashes word counts."""

    def encode(self, texts, normalize_embeddings=True):
        out = []
        for t in texts:
            v = np.zeros(8, dtype=np.float32)
            for w in t.split():
                v[hash(w) % 8] += 1.0
            if normalize_embeddings and np.linalg.norm(v) > 0:
                v = v / np.linalg.norm(v)
            out.append(v)
        return np.stack(out)


def test_indexer_indexes_md_and_persists(tmp_path: Path):
    (tmp_path / "perfil.md").write_text("Sou desenvolvedor Python há 12 anos.", encoding="utf-8")
    (tmp_path / "projeto.md").write_text("Construí um sistema de transcrição.", encoding="utf-8")
    idx = RagIndexer(knowledge_dir=tmp_path, embedder=_StubEmbedder(), chunk_size=50, overlap=5)
    n = idx.build_or_load(force=True)
    assert n >= 2
    assert (tmp_path / ".index.npz").exists()


def test_indexer_skips_when_unchanged(tmp_path: Path):
    (tmp_path / "perfil.md").write_text("conteudo", encoding="utf-8")
    idx = RagIndexer(knowledge_dir=tmp_path, embedder=_StubEmbedder(), chunk_size=50, overlap=5)
    n1 = idx.build_or_load(force=False)
    n2 = idx.build_or_load(force=False)
    assert n1 == n2
    assert idx.was_cached_last_call
```

- [ ] **Step 2: Run**

Run: `pytest tests/meeting/test_indexer.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `meeting/intelligence/rag/indexer.py`**

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from meeting.intelligence.rag.chunker import chunk_text


class _Embedder(Protocol):
    def encode(self, texts, normalize_embeddings: bool = True) -> np.ndarray: ...


@dataclass
class IndexedChunk:
    text: str
    source: str  # relative path of source file
    embedding: np.ndarray


class RagIndexer:
    INDEX_NAME = ".index.npz"

    def __init__(
        self,
        knowledge_dir: Path | str,
        embedder: _Embedder,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> None:
        self.dir = Path(knowledge_dir)
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks: list[IndexedChunk] = []
        self.was_cached_last_call = False

    def _signature(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self._iter_files()):
            try:
                stat = p.stat()
                h.update(str(p.relative_to(self.dir)).encode("utf-8"))
                h.update(str(stat.st_size).encode("utf-8"))
                h.update(str(int(stat.st_mtime)).encode("utf-8"))
            except OSError:
                continue
        h.update(str(self.chunk_size).encode())
        h.update(str(self.overlap).encode())
        return h.hexdigest()

    def _iter_files(self):
        for p in self.dir.rglob("*"):
            if not p.is_file():
                continue
            if p.name.startswith(".") or p.suffix.lower() not in {".md", ".txt", ".pdf"}:
                continue
            yield p

    def _read_file(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                return "\n".join((page.extract_text() or "") for page in reader.pages)
            except Exception:
                return ""
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def build_or_load(self, force: bool = False) -> int:
        index_path = self.dir / self.INDEX_NAME
        sig = self._signature()
        self.was_cached_last_call = False

        if not force and index_path.exists():
            with np.load(index_path, allow_pickle=True) as data:
                stored_sig = str(data["signature"])
                if stored_sig == sig:
                    embeddings = data["embeddings"]
                    texts = list(data["texts"])
                    sources = list(data["sources"])
                    self.chunks = [
                        IndexedChunk(text=t, source=s, embedding=embeddings[i])
                        for i, (t, s) in enumerate(zip(texts, sources))
                    ]
                    self.was_cached_last_call = True
                    return len(self.chunks)

        texts: list[str] = []
        sources: list[str] = []
        for p in self._iter_files():
            content = self._read_file(p)
            for chunk in chunk_text(content, self.chunk_size, self.overlap):
                if not chunk.strip():
                    continue
                texts.append(chunk)
                sources.append(str(p.relative_to(self.dir)))

        if not texts:
            self.chunks = []
            np.savez(index_path, signature=sig, embeddings=np.zeros((0, 0)), texts=[], sources=[])
            return 0

        embeddings = self.embedder.encode(texts, normalize_embeddings=True)
        self.chunks = [
            IndexedChunk(text=t, source=s, embedding=embeddings[i])
            for i, (t, s) in enumerate(zip(texts, sources))
        ]
        np.savez(
            index_path,
            signature=sig,
            embeddings=embeddings,
            texts=np.array(texts, dtype=object),
            sources=np.array(sources, dtype=object),
        )
        return len(texts)

    def matrix(self) -> np.ndarray:
        if not self.chunks:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack([c.embedding for c in self.chunks])
```

- [ ] **Step 4: Run**

Run: `pytest tests/meeting/test_indexer.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/intelligence/rag/indexer.py tests/meeting/test_indexer.py
git commit -m "feat(meeting): RAG indexer with cache invalidation by file signature"
```

---

### Task 15: RAG retriever (cosine top-k)

**Files:**
- Create: `meeting/intelligence/rag/retriever.py`
- Test: `tests/meeting/test_retriever.py`

- [ ] **Step 1: Failing test**

```python
import numpy as np

from meeting.intelligence.rag.indexer import IndexedChunk
from meeting.intelligence.rag.retriever import RagRetriever


class _StubEmbedder:
    def encode(self, texts, normalize_embeddings=True):
        out = []
        for t in texts:
            v = np.zeros(4, dtype=np.float32)
            for w in t.split():
                v[hash(w) % 4] += 1.0
            n = np.linalg.norm(v)
            if normalize_embeddings and n > 0:
                v = v / n
            out.append(v)
        return np.stack(out)


def test_retriever_returns_top_k():
    embedder = _StubEmbedder()
    docs = ["python backend", "javascript frontend", "python data"]
    embs = embedder.encode(docs)
    chunks = [IndexedChunk(text=d, source="x.md", embedding=embs[i]) for i, d in enumerate(docs)]
    retriever = RagRetriever(chunks=chunks, embedder=embedder)
    hits = retriever.retrieve("python", top_k=2)
    assert len(hits) == 2
    assert "python" in hits[0].text


def test_retriever_empty_index():
    retriever = RagRetriever(chunks=[], embedder=_StubEmbedder())
    assert retriever.retrieve("anything", top_k=3) == []
```

- [ ] **Step 2: Run**

Run: `pytest tests/meeting/test_retriever.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `meeting/intelligence/rag/retriever.py`**

```python
from __future__ import annotations

from typing import Protocol

import numpy as np

from meeting.intelligence.rag.indexer import IndexedChunk


class _Embedder(Protocol):
    def encode(self, texts, normalize_embeddings: bool = True) -> np.ndarray: ...


class RagRetriever:
    def __init__(self, chunks: list[IndexedChunk], embedder: _Embedder) -> None:
        self.chunks = chunks
        self.embedder = embedder
        if chunks:
            self._matrix = np.stack([c.embedding for c in chunks])
        else:
            self._matrix = np.zeros((0, 0), dtype=np.float32)

    def retrieve(self, query: str, top_k: int = 5) -> list[IndexedChunk]:
        if not self.chunks:
            return []
        q = self.embedder.encode([query], normalize_embeddings=True)[0]
        scores = self._matrix @ q
        order = np.argsort(-scores)[:top_k]
        return [self.chunks[int(i)] for i in order]
```

- [ ] **Step 4: Run**

Run: `pytest tests/meeting/test_retriever.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/intelligence/rag/retriever.py tests/meeting/test_retriever.py
git commit -m "feat(meeting): cosine top-k retriever"
```

---

### Task 16: `LlmClient` abstraction with Groq default

**Files:**
- Create: `meeting/intelligence/llm_client.py`
- Test: `tests/meeting/test_llm_client.py`

- [ ] **Step 1: Failing test (no real API call)**

```python
from meeting.intelligence.llm_client import LlmClient, LlmConfig, LlmMessage


class _FakeGroqClient:
    """Mimics groq.Groq().chat.completions.create()."""

    class _Resp:
        class _Choice:
            class _Msg:
                content = "Resposta gerada pela mock"
            message = _Msg()
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            return _FakeGroqClient._Resp()

    class _Chat:
        completions = _FakeGroqClient._Completions()

    chat = _Chat()


def test_llm_client_calls_provider_and_returns_text(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    cfg = LlmConfig(provider="groq", model="x", api_key_env="GROQ_API_KEY")
    client = LlmClient(cfg)
    client._groq = _FakeGroqClient()  # type: ignore[attr-defined]

    out = client.complete([LlmMessage(role="user", content="oi")])
    assert "Resposta" in out


def test_llm_client_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = LlmConfig(provider="groq", model="x", api_key_env="GROQ_API_KEY")
    client = LlmClient(cfg)
    try:
        client.complete([LlmMessage(role="user", content="oi")])
    except RuntimeError as e:
        assert "GROQ_API_KEY" in str(e)
        return
    raise AssertionError("expected RuntimeError")
```

- [ ] **Step 2: Run**

Run: `pytest tests/meeting/test_llm_client.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `meeting/intelligence/llm_client.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LlmConfig:
    provider: str           # "groq" | "anthropic" | "openai" | "local"
    model: str
    api_key_env: str = "GROQ_API_KEY"
    temperature: float = 0.4
    max_tokens: int = 400
    local_model_path: str | None = None
    local_n_ctx: int = 8192
    local_n_threads: int = 8


@dataclass
class LlmMessage:
    role: str               # "system" | "user" | "assistant"
    content: str


class LlmClient:
    """Thin abstraction. Default backend is Groq (OpenAI-compatible API).
    Tests inject `_groq` directly; real usage instantiates lazily.
    """

    def __init__(self, config: LlmConfig) -> None:
        self.config = config
        self._groq = None
        self._llama = None

    def complete(self, messages: list[LlmMessage]) -> str:
        if self.config.provider == "groq":
            return self._complete_groq(messages)
        if self.config.provider == "local":
            return self._complete_local(messages)
        raise NotImplementedError(f"provider {self.config.provider} not supported in v1")

    def _ensure_groq(self):
        if self._groq is not None:
            return
        key = os.environ.get(self.config.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"{self.config.api_key_env} env var not set; configure your Groq key"
            )
        from groq import Groq
        self._groq = Groq(api_key=key)

    def _complete_groq(self, messages: list[LlmMessage]) -> str:
        self._ensure_groq()
        assert self._groq is not None
        resp = self._groq.chat.completions.create(
            model=self.config.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _ensure_local(self):
        if self._llama is not None:
            return
        if not self.config.local_model_path:
            raise RuntimeError("local_model_path not configured")
        from llama_cpp import Llama
        self._llama = Llama(
            model_path=self.config.local_model_path,
            n_ctx=self.config.local_n_ctx,
            n_threads=self.config.local_n_threads,
            verbose=False,
        )

    def _complete_local(self, messages: list[LlmMessage]) -> str:
        self._ensure_local()
        assert self._llama is not None
        prompt_parts: list[str] = []
        for m in messages:
            prompt_parts.append(f"<|im_start|>{m.role}\n{m.content}<|im_end|>")
        prompt_parts.append("<|im_start|>assistant\n")
        prompt = "\n".join(prompt_parts)
        out = self._llama(
            prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            stop=["<|im_end|>"],
        )
        return out["choices"][0]["text"].strip()
```

- [ ] **Step 4: Run**

Run: `pytest tests/meeting/test_llm_client.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/intelligence/llm_client.py tests/meeting/test_llm_client.py
git commit -m "feat(meeting): LlmClient with Groq default and local fallback"
```

---

### Task 17: Question detector + classifier

**Files:**
- Create: `meeting/intelligence/question_detector.py`
- Create: `meeting/intelligence/classifier.py`
- Test: `tests/meeting/test_question_detector.py`
- Test: `tests/meeting/test_classifier.py`

- [ ] **Step 1: Failing tests for detector**

```python
import numpy as np

from meeting.intelligence.question_detector import QuestionDetector


def test_detects_explicit_question():
    qd = QuestionDetector()
    assert qd.is_question("qual sua experiência com python?", audio_tail=None)


def test_detects_keyword_without_punctuation():
    qd = QuestionDetector()
    assert qd.is_question("me conta um pouco sobre você", audio_tail=None)


def test_rejects_statement():
    qd = QuestionDetector()
    assert not qd.is_question("entendi tudo certo aqui", audio_tail=None)


def test_prosody_pushes_borderline_to_question():
    qd = QuestionDetector()
    tail = np.concatenate([
        np.ones(int(0.3 * 16000), dtype=np.float32) * 0.05,  # quiet body
        np.ones(int(0.3 * 16000), dtype=np.float32) * 0.4,   # loud tail
    ])
    # Statement with no question marks/keywords but rising tail → still false
    assert not qd.is_question("sim certo", audio_tail=tail)
    # Statement with one keyword + rising tail → true (2 of 3)
    assert qd.is_question("você consegue isso", audio_tail=tail)
```

- [ ] **Step 2: Failing tests for classifier**

```python
from meeting.intelligence.classifier import Classifier
from meeting.intelligence.types import SuggestionKind


class _StubLlm:
    def __init__(self, answer: str): self.answer = answer
    def complete(self, messages): return self.answer


def test_classifier_returns_personal():
    c = Classifier(llm=_StubLlm("A"), model="x")
    assert c.classify("conta sobre sua experiência", "") is SuggestionKind.PERSONAL


def test_classifier_returns_technical():
    c = Classifier(llm=_StubLlm("B"), model="x")
    assert c.classify("como funciona OAuth", "") is SuggestionKind.TECHNICAL


def test_classifier_returns_hybrid_for_unclear():
    c = Classifier(llm=_StubLlm("C"), model="x")
    assert c.classify("...", "") is SuggestionKind.HYBRID


def test_classifier_defaults_to_hybrid_on_garbage():
    c = Classifier(llm=_StubLlm("???"), model="x")
    assert c.classify("...", "") is SuggestionKind.HYBRID
```

- [ ] **Step 3: Run both, verify FAIL**

Run: `pytest tests/meeting/test_question_detector.py tests/meeting/test_classifier.py -v`

- [ ] **Step 4: Implement `meeting/intelligence/question_detector.py`**

```python
from __future__ import annotations

import numpy as np


_KEYWORDS = (
    "como ", "por que ", "porque ", "qual ", "quando ", "onde ", "quem ",
    "o que ", "que tal ", "cadê ", "me conta", "me fala", "você ",
    "pra você", "na sua opinião", "experiência", "já trabalhou",
    "entende de", "sabe ", "saberia ", "consegue ", "explica",
)


class QuestionDetector:
    """Heuristic question detection. 2 of 3 wins:
    1. text ends with '?'
    2. matches keyword list
    3. prosody: tail RMS >= 1.3 * mean RMS of head
    """

    def __init__(self, prosody_ratio: float = 1.3) -> None:
        self.prosody_ratio = prosody_ratio

    def _keyword_hit(self, text: str) -> bool:
        t = " " + text.lower().strip() + " "
        return any(k in t for k in _KEYWORDS)

    def _prosody_rising(self, audio: np.ndarray | None) -> bool:
        if audio is None or audio.size < int(0.5 * 16000):
            return False
        tail_size = int(0.3 * 16000)
        head = audio[: -tail_size] if audio.size > tail_size else audio
        tail = audio[-tail_size:]
        head_rms = float(np.sqrt(np.mean(np.square(head)))) if head.size else 1e-9
        tail_rms = float(np.sqrt(np.mean(np.square(tail)))) if tail.size else 0.0
        if head_rms <= 1e-6:
            return False
        return tail_rms / head_rms >= self.prosody_ratio

    def is_question(self, text: str, audio_tail: np.ndarray | None) -> bool:
        signals = 0
        if text.strip().endswith("?"):
            signals += 1
        if self._keyword_hit(text):
            signals += 1
        if self._prosody_rising(audio_tail):
            signals += 1
        return signals >= 2
```

- [ ] **Step 5: Implement `meeting/intelligence/classifier.py`**

```python
from __future__ import annotations

from typing import Protocol

from meeting.intelligence.types import SuggestionKind


class _Llm(Protocol):
    def complete(self, messages) -> str: ...


_PROMPT = """\
Classifique a pergunta abaixo em uma única letra:
A) Pessoal — sobre experiência, opinião ou trajetória do entrevistado.
B) Técnica — conhecimento de domínio, conceito, definição.
C) Híbrida — técnica que pede experiência pessoal.

Responda apenas A, B ou C.

Pergunta: {q}
Contexto recente da reunião:
{ctx}
"""


class Classifier:
    def __init__(self, llm: _Llm, model: str) -> None:
        self.llm = llm
        self.model = model

    def classify(self, question: str, context: str) -> SuggestionKind:
        from meeting.intelligence.llm_client import LlmMessage
        msgs = [LlmMessage(role="user", content=_PROMPT.format(q=question, ctx=context))]
        try:
            answer = self.llm.complete(msgs).strip().upper()
        except Exception:
            return SuggestionKind.HYBRID
        if "A" in answer[:3]:
            return SuggestionKind.PERSONAL
        if "B" in answer[:3]:
            return SuggestionKind.TECHNICAL
        return SuggestionKind.HYBRID
```

- [ ] **Step 6: Run both tests, verify PASS**

Run: `pytest tests/meeting/test_question_detector.py tests/meeting/test_classifier.py -v`
Expected: 8 PASS.

- [ ] **Step 7: Commit**

```bash
git add meeting/intelligence/question_detector.py meeting/intelligence/classifier.py tests/meeting/test_question_detector.py tests/meeting/test_classifier.py
git commit -m "feat(meeting): question detector heuristics + LLM classifier"
```

---

### Task 18: `Responder` orchestrating the full intelligence path

**Files:**
- Create: `meeting/intelligence/responder.py`
- Test: `tests/meeting/test_responder.py`

- [ ] **Step 1: Failing test**

```python
import numpy as np

from meeting.intelligence.rag.indexer import IndexedChunk
from meeting.intelligence.rag.retriever import RagRetriever
from meeting.intelligence.responder import Responder
from meeting.intelligence.types import SuggestionKind


class _StubEmbedder:
    def encode(self, texts, normalize_embeddings=True):
        return np.ones((len(texts), 2), dtype=np.float32) / np.sqrt(2)


class _StubLlm:
    def __init__(self): self.calls = []
    def complete(self, messages):
        self.calls.append(messages)
        return "minha resposta"


def test_responder_personal_uses_rag():
    emb = _StubEmbedder()
    chunks = [IndexedChunk("python backend", "p.md", emb.encode(["python backend"])[0])]
    retriever = RagRetriever(chunks, emb)
    llm = _StubLlm()
    r = Responder(retriever=retriever, classifier=lambda q, c: SuggestionKind.PERSONAL,
                  llm=llm, model="x", system_prompt_personal="VOCE EH FERNANDO")
    s = r.respond(question="conta sua experiência", recent_context="")
    assert s.kind is SuggestionKind.PERSONAL
    assert "python backend" in llm.calls[0][-1].content
    assert "VOCE EH FERNANDO" in llm.calls[0][0].content


def test_responder_technical_skips_rag():
    emb = _StubEmbedder()
    chunks = [IndexedChunk("python", "p.md", emb.encode(["python"])[0])]
    retriever = RagRetriever(chunks, emb)
    llm = _StubLlm()
    r = Responder(retriever=retriever, classifier=lambda q, c: SuggestionKind.TECHNICAL,
                  llm=llm, model="x")
    s = r.respond(question="como funciona OAuth", recent_context="")
    assert s.kind is SuggestionKind.TECHNICAL
    assert "python" not in llm.calls[0][-1].content
```

- [ ] **Step 2: Run, verify FAIL**

Run: `pytest tests/meeting/test_responder.py -v`

- [ ] **Step 3: Implement `meeting/intelligence/responder.py`**

```python
from __future__ import annotations

import uuid
from typing import Callable

from meeting.intelligence.llm_client import LlmMessage
from meeting.intelligence.rag.retriever import RagRetriever
from meeting.intelligence.types import Suggestion, SuggestionKind


_SYSTEM_PERSONAL_DEFAULT = (
    "Você está auxiliando um entrevistado numa reunião. "
    "Responda na primeira pessoa, profissional, direto, máximo 4 frases, em português. "
    "Use os trechos do perfil/CV abaixo como base. Não invente fatos não presentes nos trechos."
)
_SYSTEM_TECHNICAL_DEFAULT = (
    "Responda tecnicamente como se estivesse explicando numa entrevista. "
    "Claro, exemplos práticos, máximo 4 frases. Em português, mantendo termos técnicos em inglês."
)
_SYSTEM_HYBRID_DEFAULT = (
    "Combine conhecimento técnico padrão com a experiência pessoal nos trechos abaixo. "
    "Responda na primeira pessoa, máximo 4 frases. Em português."
)


class Responder:
    """Glues classifier + RAG + LLM into one Suggestion per question."""

    def __init__(
        self,
        retriever: RagRetriever,
        classifier: Callable[[str, str], SuggestionKind],
        llm,
        model: str,
        top_k: int = 5,
        system_prompt_personal: str = _SYSTEM_PERSONAL_DEFAULT,
        system_prompt_technical: str = _SYSTEM_TECHNICAL_DEFAULT,
        system_prompt_hybrid: str = _SYSTEM_HYBRID_DEFAULT,
    ) -> None:
        self.retriever = retriever
        self.classifier = classifier
        self.llm = llm
        self.model = model
        self.top_k = top_k
        self.system_prompts = {
            SuggestionKind.PERSONAL: system_prompt_personal,
            SuggestionKind.TECHNICAL: system_prompt_technical,
            SuggestionKind.HYBRID: system_prompt_hybrid,
        }

    def respond(self, question: str, recent_context: str) -> Suggestion:
        kind = self.classifier(question, recent_context)
        used: list[str] = []

        retrieved_block = ""
        if kind in (SuggestionKind.PERSONAL, SuggestionKind.HYBRID):
            hits = self.retriever.retrieve(f"{question}\n\n{recent_context}", top_k=self.top_k)
            if hits:
                blocks = []
                for h in hits:
                    blocks.append(f"[{h.source}]\n{h.text}")
                    used.append(h.source)
                retrieved_block = "\n\nTrechos relevantes:\n" + "\n---\n".join(blocks)

        user_prompt = (
            f"Pergunta: {question}\n\n"
            f"Contexto recente da reunião:\n{recent_context or '(vazio)'}"
            f"{retrieved_block}"
        )
        messages = [
            LlmMessage(role="system", content=self.system_prompts[kind]),
            LlmMessage(role="user", content=user_prompt),
        ]
        text = self.llm.complete(messages)
        return Suggestion(
            kind=kind,
            text=text,
            source_turn_id=uuid.uuid4().hex,
            used_chunks=tuple(used),
        )
```

- [ ] **Step 4: Run, verify PASS**

Run: `pytest tests/meeting/test_responder.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting/intelligence/responder.py tests/meeting/test_responder.py
git commit -m "feat(meeting): Responder orchestrating classifier+RAG+LLM"
```

---

### Task 19: Summarizer

**Files:**
- Create: `meeting/intelligence/summarizer.py`
- Test: `tests/meeting/test_summarizer.py`

- [ ] **Step 1: Failing test**

```python
from datetime import datetime

from meeting.intelligence.summarizer import Summarizer
from meeting.transcribe.turn import Speaker, Turn


class _StubLlm:
    def complete(self, messages):
        return "## Tópicos\n- A\n## Action items\n- foo"


def test_summarizer_returns_markdown():
    s = Summarizer(llm=_StubLlm(), model="x")
    turns = [Turn(Speaker.THEM, 0, 1, "ola", datetime.now()),
             Turn(Speaker.YOU, 1, 2, "oi", datetime.now())]
    md = s.summarize(turns)
    assert "Tópicos" in md
    assert "Action items" in md
```

- [ ] **Step 2: Run, FAIL**

Run: `pytest tests/meeting/test_summarizer.py -v`

- [ ] **Step 3: Implement `meeting/intelligence/summarizer.py`**

```python
from __future__ import annotations

from meeting.intelligence.llm_client import LlmMessage
from meeting.transcribe.turn import Turn


_SYSTEM = (
    "Você é um assistente que sumariza reuniões em Markdown. Gere seções: "
    "## Resumo, ## Tópicos discutidos, ## Decisões, ## Action items (com responsável quando claro). "
    "Em português. Seja conciso."
)


class Summarizer:
    def __init__(self, llm, model: str) -> None:
        self.llm = llm
        self.model = model

    def summarize(self, turns: list[Turn]) -> str:
        if not turns:
            return "## Resumo\nReunião sem turnos transcritos.\n"
        body = "\n".join(t.to_line() for t in turns)
        msgs = [
            LlmMessage(role="system", content=_SYSTEM),
            LlmMessage(role="user", content=f"Transcrição:\n\n{body}"),
        ]
        try:
            return self.llm.complete(msgs)
        except Exception as e:
            return f"## Resumo\n_Falha ao gerar sumário automático: {e}_\n"
```

- [ ] **Step 4: Run, PASS**

Run: `pytest tests/meeting/test_summarizer.py -v`

- [ ] **Step 5: Commit**

```bash
git add meeting/intelligence/summarizer.py tests/meeting/test_summarizer.py
git commit -m "feat(meeting): markdown summarizer"
```

---

## Phase 6 — UI

### Task 20: Capture-invisibility helper

**Files:**
- Create: `meeting/ui/invisibility.py`
- Test: `tests/meeting/test_invisibility.py`

- [ ] **Step 1: Failing test (mocked Win32 call)**

```python
from unittest.mock import MagicMock

from meeting.ui.invisibility import set_window_invisible_to_capture


def test_invisibility_calls_set_display_affinity(monkeypatch):
    fake_user32 = MagicMock()
    fake_user32.SetWindowDisplayAffinity.return_value = 1
    monkeypatch.setattr(
        "meeting.ui.invisibility._user32",
        lambda: fake_user32,
    )
    ok = set_window_invisible_to_capture(hwnd=12345, enabled=True)
    assert ok is True
    fake_user32.SetWindowDisplayAffinity.assert_called_once()
    args = fake_user32.SetWindowDisplayAffinity.call_args.args
    assert args[0] == 12345


def test_invisibility_returns_false_on_failure(monkeypatch):
    fake_user32 = MagicMock()
    fake_user32.SetWindowDisplayAffinity.return_value = 0
    monkeypatch.setattr("meeting.ui.invisibility._user32", lambda: fake_user32)
    assert set_window_invisible_to_capture(hwnd=1, enabled=True) is False
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement `meeting/ui/invisibility.py`**

```python
from __future__ import annotations

import ctypes


WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 2004+


def _user32():
    return ctypes.windll.user32  # type: ignore[attr-defined]


def set_window_invisible_to_capture(hwnd: int, enabled: bool) -> bool:
    """Apply or remove the WDA_EXCLUDEFROMCAPTURE flag on a window handle.

    Returns True on success, False if the API call failed (older Windows or
    unprivileged process).
    """
    flag = WDA_EXCLUDEFROMCAPTURE if enabled else WDA_NONE
    try:
        result = _user32().SetWindowDisplayAffinity(int(hwnd), flag)
    except Exception:
        return False
    return bool(result)
```

- [ ] **Step 4: Run, PASS**

Run: `pytest tests/meeting/test_invisibility.py -v`

- [ ] **Step 5: Commit**

```bash
git add meeting/ui/invisibility.py tests/meeting/test_invisibility.py
git commit -m "feat(meeting): WDA_EXCLUDEFROMCAPTURE wrapper"
```

---

### Task 21: `SuggestionCard` widget

**Files:**
- Create: `meeting/ui/suggestion_card.py`

(Pragmatic — Qt widgets are tested manually. Add file, smoke-import.)

- [ ] **Step 1: Implement `meeting/ui/suggestion_card.py`**

```python
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from meeting.intelligence.types import Suggestion, SuggestionKind


_KIND_VISUAL = {
    SuggestionKind.PERSONAL:  ("🧠 Pessoal",  QColor(120, 100, 30)),
    SuggestionKind.TECHNICAL: ("📚 Técnica",  QColor(40, 80, 140)),
    SuggestionKind.HYBRID:    ("🔀 Híbrida",  QColor(110, 60, 150)),
}


class SuggestionCard(QFrame):
    use_clicked = Signal(str)
    dismiss_clicked = Signal()

    def __init__(self, suggestion: Suggestion, parent=None) -> None:
        super().__init__(parent)
        self.suggestion = suggestion
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        label_text, color = _KIND_VISUAL[suggestion.kind]
        self.setStyleSheet(
            f"QFrame {{ background-color: rgba({color.red()},{color.green()},{color.blue()},230);"
            f"  border-radius: 10px; }} QLabel {{ color: white; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(f"💡 SUGESTÃO  {label_text}")
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title, 1)

        use_btn = QPushButton("✓ Usar")
        use_btn.clicked.connect(lambda: self.use_clicked.emit(suggestion.text))
        header.addWidget(use_btn)

        dismiss_btn = QPushButton("✕")
        dismiss_btn.clicked.connect(self.dismiss_clicked.emit)
        header.addWidget(dismiss_btn)

        layout.addLayout(header)

        body = QLabel(suggestion.text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)
```

- [ ] **Step 2: Smoke test (import only)**

Run: `python -c "from meeting.ui.suggestion_card import SuggestionCard; print('ok')"`
Expected: `ok`. (Will fail if PySide6 import broken; verifies syntax.)

- [ ] **Step 3: Commit**

```bash
git add meeting/ui/suggestion_card.py
git commit -m "feat(meeting): suggestion card widget"
```

---

### Task 22: `TranscriptView` widget

**Files:**
- Create: `meeting/ui/transcript_view.py`

- [ ] **Step 1: Implement**

```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QTextEdit

from meeting.transcribe.turn import Speaker, Turn


_SPEAKER_COLOR = {
    Speaker.YOU: "#7CFFA8",   # green
    Speaker.THEM: "#7CC4FF",  # blue
}


class TranscriptView(QTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("background-color: #101014; color: #DDDDE5; padding: 8px;")
        self.setFont(QFont("Consolas", 10))
        self._auto_scroll = True
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, value: int) -> None:
        bar = self.verticalScrollBar()
        self._auto_scroll = value >= bar.maximum() - 4

    def append_turn(self, turn: Turn) -> None:
        ts = turn.wall_clock.strftime("%H:%M:%S")
        color = _SPEAKER_COLOR[turn.speaker]
        speaker_box = f"[{turn.speaker.value}]".ljust(8)
        html = (
            f'<div style="margin: 0 0 4px 0;">'
            f'<span style="color:#666;">{ts}</span> '
            f'<span style="color:{color}; font-weight: bold;">{speaker_box}</span> '
            f'<span style="color:#DDDDE5;">{self._escape(turn.text)}</span>'
            f"</div>"
        )
        self.append(html)
        if self._auto_scroll:
            self.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
```

- [ ] **Step 2: Smoke test**

Run: `python -c "from meeting.ui.transcript_view import TranscriptView; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add meeting/ui/transcript_view.py
git commit -m "feat(meeting): transcript view widget"
```

---

### Task 23: `LiveWindow` — main meeting window

**Files:**
- Create: `meeting/ui/live_window.py`

- [ ] **Step 1: Implement `meeting/ui/live_window.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from meeting.intelligence.types import Suggestion
from meeting.transcribe.turn import Turn
from meeting.ui.invisibility import set_window_invisible_to_capture
from meeting.ui.suggestion_card import SuggestionCard
from meeting.ui.transcript_view import TranscriptView


STATE_FILE = Path("meeting/.window_state.json")


class LiveWindow(QWidget):
    pause_requested = Signal()
    stop_requested = Signal()
    force_suggest_requested = Signal()

    def __init__(self, opacity: float = 0.92) -> None:
        flags = Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setWindowOpacity(opacity)
        self.setWindowTitle("Sussurro Meeting")
        self.setMinimumSize(540, 360)
        self.setStyleSheet("background-color: #14141A; color: #DDDDE5;")

        self._invisible = True
        self._build_ui()
        self._restore_geometry()

        # Apply invisibility after first show so winId() is valid.
        QTimer.singleShot(0, self._apply_invisibility)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Sussurro Meeting")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(title)

        self._invis_label = QLabel("🛡️ Invisível")
        self._invis_label.setStyleSheet("color: #7CFFA8;")
        header.addWidget(self._invis_label)

        header.addStretch(1)

        pause_btn = QPushButton("⏸ Pausar")
        pause_btn.clicked.connect(self.pause_requested.emit)
        header.addWidget(pause_btn)
        stop_btn = QPushButton("⏹ Parar")
        stop_btn.clicked.connect(self.stop_requested.emit)
        header.addWidget(stop_btn)
        outer.addLayout(header)

        self._suggestions_holder = QVBoxLayout()
        outer.addLayout(self._suggestions_holder)

        self.transcript = TranscriptView()
        outer.addWidget(self.transcript, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        force_btn = QPushButton("🔁 Forçar sugestão")
        force_btn.clicked.connect(self.force_suggest_requested.emit)
        bottom.addWidget(force_btn)
        outer.addLayout(bottom)

        QShortcut(QKeySequence("Esc"), self, activated=self._dismiss_current)
        QShortcut(QKeySequence("Return"), self, activated=self._use_current)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.pause_requested.emit)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.stop_requested.emit)

        self._current_card: SuggestionCard | None = None
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._dismiss_current)

    # ---- public API ----

    def append_turn(self, turn: Turn) -> None:
        self.transcript.append_turn(turn)

    def show_suggestion(self, suggestion: Suggestion, ttl_seconds: int) -> None:
        self._dismiss_current()
        card = SuggestionCard(suggestion)
        card.use_clicked.connect(self._copy_to_clipboard)
        card.dismiss_clicked.connect(self._dismiss_current)
        self._suggestions_holder.addWidget(card)
        self._current_card = card
        self._dismiss_timer.start(ttl_seconds * 1000)

    # ---- private helpers ----

    def _copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self._dismiss_current()

    def _dismiss_current(self) -> None:
        if self._current_card is None:
            return
        self._current_card.deleteLater()
        self._current_card = None
        self._dismiss_timer.stop()

    def _use_current(self) -> None:
        if self._current_card is not None:
            self._copy_to_clipboard(self._current_card.suggestion.text)

    def _apply_invisibility(self) -> None:
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        ok = set_window_invisible_to_capture(hwnd=hwnd, enabled=self._invisible)
        self._invis_label.setText("🛡️ Invisível" if ok and self._invisible else "👁️ Visível")
        self._invis_label.setStyleSheet(
            "color: #7CFFA8;" if ok and self._invisible else "color: #FFB05E;"
        )

    def _restore_geometry(self) -> None:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.setGeometry(data["x"], data["y"], data["w"], data["h"])
        except Exception:
            self.resize(720, 480)

    def closeEvent(self, event) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            geom = self.geometry()
            STATE_FILE.write_text(
                json.dumps({"x": geom.x(), "y": geom.y(), "w": geom.width(), "h": geom.height()}),
                encoding="utf-8",
            )
        except Exception:
            pass
        super().closeEvent(event)
```

- [ ] **Step 2: Smoke test**

Run: `python -c "from meeting.ui.live_window import LiveWindow; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add meeting/ui/live_window.py
git commit -m "feat(meeting): LiveWindow with shortcuts, geometry persistence, invisibility"
```

---

### Task 24: Smoke-run the LiveWindow standalone

**Files:**
- Create: `meeting/ui/_smoke_live.py` (script, not part of normal flow)

- [ ] **Step 1: Implement smoke script**

```python
from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from meeting.intelligence.types import Suggestion, SuggestionKind
from meeting.transcribe.turn import Speaker, Turn
from meeting.ui.live_window import LiveWindow


def main() -> None:
    app = QApplication(sys.argv)
    win = LiveWindow()
    win.show()

    win.append_turn(Turn(Speaker.THEM, 0, 1, "Olá pessoal", datetime.now()))
    win.append_turn(Turn(Speaker.YOU, 1, 2, "Bom dia", datetime.now()))

    QTimer.singleShot(
        500,
        lambda: win.show_suggestion(
            Suggestion(kind=SuggestionKind.HYBRID, text="resposta sugerida.", source_turn_id="x"),
            ttl_seconds=15,
        ),
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual run (optional but recommended)**

Run: `python -m meeting.ui._smoke_live`
Expected: window appears with two transcript lines and a suggestion card.

- [ ] **Step 3: Commit**

```bash
git add meeting/ui/_smoke_live.py
git commit -m "chore(meeting): standalone smoke runner for LiveWindow"
```

---

## Phase 7 — Controller + integration

### Task 25: `MeetingController` — the orchestrator

**Files:**
- Create: `meeting/controller.py`
- Test: `tests/meeting/test_controller.py`

- [ ] **Step 1: Failing test (heavy use of fakes)**

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from meeting.controller import MeetingController, MeetingDeps
from meeting.intelligence.types import Suggestion, SuggestionKind
from meeting.state import MeetingState
from meeting.transcribe.turn import Speaker, Turn


def _make_deps(tmp_path: Path) -> MeetingDeps:
    return MeetingDeps(
        mic_capture=MagicMock(),
        system_capture=MagicMock(),
        pipeline=MagicMock(),
        responder=MagicMock(),
        summarizer=MagicMock(),
        session_writer_factory=MagicMock(),
        live_window=MagicMock(),
        question_detector=MagicMock(),
        config={"intelligence": {"context_window_minutes": 2, "suggestion_ttl_seconds": 90,
                                  "auto_suggest": True, "question_detection": True},
                "storage": {"output_dir": str(tmp_path)}},
    )


def test_controller_starts_pipeline_and_changes_state(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    c = MeetingController(deps)

    c.start()

    assert c.state is MeetingState.RECORDING
    deps.mic_capture.open.assert_called_once()
    deps.system_capture.open.assert_called_once()
    deps.pipeline.start.assert_called_once()
    sw.start.assert_called_once()


def test_controller_routes_turn_to_writer_window_and_questiondet(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    deps.question_detector.is_question.return_value = False
    c = MeetingController(deps)
    c.start()

    turn = Turn(Speaker.THEM, 0, 1, "ola", datetime.now())
    c._on_turn(turn)

    sw.append_turn.assert_called_once_with(turn)
    deps.live_window.append_turn.assert_called_once_with(turn)
    deps.question_detector.is_question.assert_called_once()


def test_controller_emits_suggestion_when_question(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    deps.question_detector.is_question.return_value = True
    deps.responder.respond.return_value = Suggestion(SuggestionKind.PERSONAL, "ans", "t1")
    c = MeetingController(deps)
    c.start()
    turn = Turn(Speaker.THEM, 0, 1, "qual sua experiência?", datetime.now())
    c._on_turn(turn)
    deps.responder.respond.assert_called_once()
    deps.live_window.show_suggestion.assert_called_once()


def test_controller_stop_finalizes_writer_and_summary(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    deps.summarizer.summarize.return_value = "## Resumo"
    c = MeetingController(deps)
    c.start()
    c._on_turn(Turn(Speaker.YOU, 0, 1, "oi", datetime.now()))
    c.stop()

    deps.pipeline.stop.assert_called_once()
    deps.mic_capture.close.assert_called_once()
    deps.system_capture.close.assert_called_once()
    deps.summarizer.summarize.assert_called_once()
    sw.finalize.assert_called_once_with(summary="## Resumo")
    assert c.state is MeetingState.STOPPED
```

- [ ] **Step 2: Run, FAIL**

Run: `pytest tests/meeting/test_controller.py -v`

- [ ] **Step 3: Implement `meeting/controller.py`**

```python
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
    audio in → buffers → pipeline → on_turn → writer/window/intelligence.
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

    def stop(self) -> None:
        if self.state is MeetingState.STOPPED:
            return
        try: self.deps.mic_capture.close()
        except Exception: pass
        try: self.deps.system_capture.close()
        except Exception: pass
        # flush remaining audio in buffers
        try: self._buf_them.on_turn_end()
        except Exception: pass
        try: self._buf_you.on_turn_end()
        except Exception: pass
        try: self.deps.pipeline.stop()
        except Exception: pass

        try:
            summary = self.deps.summarizer.summarize(self._turns)
        except Exception as e:
            summary = f"## Resumo\n_Falha ao gerar sumário: {e}_\n"

        if self._writer is not None:
            try:
                self._writer.finalize(summary=summary)
            except Exception:
                pass

        self.state = MeetingState.STOPPED

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
            try: self._writer.append_turn(turn)
            except Exception: pass
        try: self.deps.live_window.append_turn(turn)
        except Exception: pass

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
```

- [ ] **Step 4: Wire `pipeline.on_turn` to controller in test setup**

Update test to set `deps.pipeline.on_turn = c._on_turn`. Re-run.

Edit `tests/meeting/test_controller.py`, replace each `c = MeetingController(deps); c.start()` with:

```python
c = MeetingController(deps)
c.start()
deps.pipeline.on_turn = c._on_turn  # wired by app code in real usage
```

- [ ] **Step 5: Run, PASS**

Run: `pytest tests/meeting/test_controller.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add meeting/controller.py tests/meeting/test_controller.py
git commit -m "feat(meeting): MeetingController orchestrator"
```

---

### Task 26: Wire controller in `src/app.py` — bubble menu integration

**Files:**
- Modify: `src/app.py`
- Modify: `src/overlay.py` (context menu items)

- [ ] **Step 1: Read current `src/app.py` and `src/overlay.py`**

Run: `cat src/app.py src/overlay.py | head -400`
Expected: see existing structure to know where to inject.

- [ ] **Step 2: Add a "Iniciar reunião" entry to the context menu**

In `src/overlay.py`, find `def contextMenuEvent` and add an item before the existing "Sair":

```python
self.start_meeting_action = QAction("Iniciar reunião", self)
self.start_meeting_action.triggered.connect(self.meeting_toggle_requested.emit)
menu.addAction(self.start_meeting_action)
menu.addSeparator()
```

Add at the top of the class, alongside `quit_requested`:

```python
meeting_toggle_requested = Signal()
```

Add a method:

```python
def set_meeting_active(self, active: bool) -> None:
    self.start_meeting_action.setText("Parar reunião" if active else "Iniciar reunião")
```

- [ ] **Step 3: In `src/app.py`, in `SussurroApp.__init__`, connect the signal**

Add after `self.overlay.quit_requested.connect(self._quit)`:

```python
self.overlay.meeting_toggle_requested.connect(self._toggle_meeting)
self._meeting_controller = None
self._meeting_window = None
```

Add the toggle method on `SussurroApp`:

```python
def _toggle_meeting(self) -> None:
    if self._meeting_controller is None or self._meeting_controller.state.value == "stopped":
        self._start_meeting()
    else:
        self._stop_meeting()


def _start_meeting(self) -> None:
    from pathlib import Path
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

    cfg_path = Path(__file__).resolve().parent.parent / "meeting" / "meeting_config.yaml"
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    transcriber = MeetingTranscriber(
        model_size=config["transcribe"]["model"],
        language=config["transcribe"]["language"],
        download_root=Path("models"),
    )
    pipeline = TranscribePipeline(
        transcriber=transcriber,
        on_turn=lambda t: None,  # rebound below after controller exists
        workers=config["transcribe"]["parallel_workers"],
    )
    llm_main = LlmClient(LlmConfig(
        provider=config["llm"]["provider"],
        model=config["llm"]["model"],
        api_key_env=config["llm"]["api_key_env"],
        local_model_path=config["llm"].get("local", {}).get("model_path"),
    ))
    llm_classifier = LlmClient(LlmConfig(
        provider=config["llm"]["provider"],
        model=config["llm"]["classifier_model"],
        api_key_env=config["llm"]["api_key_env"],
        max_tokens=4,
    ))

    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer(config["rag"]["embedding_model"])
    indexer = RagIndexer(
        knowledge_dir=Path(config["rag"]["knowledge_dir"]),
        embedder=embedder,
        chunk_size=config["rag"]["chunk_size"],
        overlap=config["rag"]["chunk_overlap"],
    )
    indexer.build_or_load()
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

    self._meeting_window = LiveWindow(opacity=config["ui"]["opacity"])
    self._meeting_window.show()

    deps = MeetingDeps(
        mic_capture=MicCapture(),
        system_capture=SystemCapture(),
        pipeline=pipeline,
        responder=responder,
        summarizer=summarizer,
        session_writer_factory=lambda sid: SessionWriter(
            root=Path(config["storage"]["output_dir"]),
            session_id=sid,
        ),
        live_window=self._meeting_window,
        question_detector=QuestionDetector(),
        config=config,
    )
    self._meeting_controller = MeetingController(deps)
    pipeline.on_turn = self._meeting_controller._on_turn  # rewire pipeline output

    self._meeting_window.pause_requested.connect(self._noop)
    self._meeting_window.stop_requested.connect(self._stop_meeting)
    self._meeting_window.force_suggest_requested.connect(self._force_suggest)

    self._meeting_controller.start()
    self.overlay.set_meeting_active(True)


def _force_suggest(self) -> None:
    if self._meeting_controller is None: return
    last_them = next(
        (t for t in reversed(self._meeting_controller._turns) if t.speaker.value == "Eles"),
        None,
    )
    if last_them is None: return
    import threading
    threading.Thread(
        target=self._meeting_controller._respond_async, args=(last_them,), daemon=True
    ).start()


def _stop_meeting(self) -> None:
    if self._meeting_controller is not None:
        self._meeting_controller.stop()
        self._meeting_controller = None
    if self._meeting_window is not None:
        self._meeting_window.close()
        self._meeting_window = None
    self.overlay.set_meeting_active(False)


def _noop(self) -> None:
    pass
```

- [ ] **Step 4: Smoke run (verify imports/syntax)**

Run: `python -c "from src.app import SussurroApp; print('ok')"`
Expected: `ok`. Any import error here is the bug — fix it.

- [ ] **Step 5: Commit**

```bash
git add src/app.py src/overlay.py
git commit -m "feat(meeting): integrate meeting controller with bubble context menu"
```

---

### Task 27: Add `meeting/` and `knowledge/` to PyInstaller spec

**Files:**
- Modify: `Sussurro.spec`

- [ ] **Step 1: Read existing `Sussurro.spec`**

Run: `cat Sussurro.spec`

- [ ] **Step 2: Add hidden imports and data files**

In the existing `hidden = []` section, append:

```python
hidden += collect_submodules("meeting")
hidden += collect_submodules("sentence_transformers")
hidden += collect_submodules("silero_vad")
hidden += collect_submodules("groq")
hidden += collect_submodules("pypdf")
hidden += collect_submodules("pyaudiowpatch")
hidden += ["win32api", "win32con"]
```

In the `datas = []` section, append:

```python
datas += [("meeting/meeting_config.yaml", "meeting")]
datas += collect_data_files("sentence_transformers")
datas += collect_data_files("silero_vad")
```

In `excludes`, **remove** `"av"` if present (already removed in earlier work, double-check). Also keep `"torch"` excluded only if `sentence-transformers` doesn't pull torch — verify by trying the build. If build fails missing torch, remove `"torch"` from excludes.

- [ ] **Step 3: Test build**

Run: `python -m PyInstaller Sussurro.spec --noconfirm --clean 2>&1 | tail -10`
Expected: `Build complete!`. If it fails, read the error and adjust hidden imports/excludes.

- [ ] **Step 4: Commit**

```bash
git add Sussurro.spec
git commit -m "build(meeting): include meeting deps in PyInstaller spec"
```

---

## Phase 8 — Build, smoke and docs

### Task 28: README addition for meeting mode

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append a new section to the existing README**

Append at the end of `README.md`:

```markdown
## Meeting Mode

Sussurro também transcreve reuniões do Teams/Meet/Zoom em duas trilhas (você + outros), gera sumário e sugere respostas a perguntas direcionadas a você.

### Setup

1. **Pasta `knowledge/`** — edite `knowledge/perfil.md` com sua bio, experiência, skills, valores. Adicione PDFs/MDs em `knowledge/projetos/` ou `knowledge/tecnico/` se quiser.
2. **Crie conta grátis na Groq** em https://groq.com → API Keys → Create API Key. Copie.
3. **Defina a env var** (PowerShell, perpétuo):
   ```powershell
   setx GROQ_API_KEY "<sua-key>"
   ```
   Reinicie o terminal/Sussurro pra a env var aparecer.

### Uso

1. Inicie sua reunião do Teams/Meet/Zoom.
2. **Clique direito na bolinha do Sussurro** → "Iniciar reunião".
3. Janela ao vivo aparece, invisível pra captura de tela.
4. Conforme as pessoas falam, transcrição rola na tela.
5. Quando alguém te faz pergunta, card de sugestão aparece com a resposta.
6. **Ctrl+Q** ou clique direito → "Parar reunião".
7. Saída em `reunioes/YYYY-MM-DD_HH-MM/`: `transcript.txt` + `sumario.md`.

### Atalhos com a janela em foco

- `Esc` — descarta sugestão
- `Enter` — copia sugestão pro clipboard
- `Ctrl+P` — pausa/retoma captura
- `Ctrl+Q` — encerra reunião

### Privacidade

Default usa Groq (Llama 3.3 70B grátis). Sua transcrição vai pra Groq via HTTPS, não é treinada (política deles). Pra 100% local, edite `meeting/meeting_config.yaml`:

```yaml
llm:
  provider: local
  local:
    model_path: models/llm/qwen2.5-7b-instruct-q4_k_m.gguf
```

Depois `pip install llama-cpp-python` e baixe o GGUF de qwen2.5-7b em https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF.

### Limitações

- Só Windows 10 (build 2004+) ou Windows 11 — usa WASAPI loopback e `WDA_EXCLUDEFROMCAPTURE`.
- Falsos positivos/negativos na detecção de pergunta — botão "Forçar sugestão" pra disparar manual.
- Modo entrevistado em entrevista de emprego pode ser considerado fraude no contexto. Use com responsabilidade.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(meeting): add Meeting Mode section to README"
```

---

### Task 29: End-to-end smoke test (manual)

**Files:** none (manual checklist)

- [ ] **Step 1: Start a Teams call with a teammate (or a YouTube video as a stand-in)**

- [ ] **Step 2: Run `python main.py` and click right on the bubble → "Iniciar reunião"**

Expected: live window appears in the corner, transcription starts within 5s.

- [ ] **Step 3: Speak a sentence into the mic**

Expected: line appears as `[Você]` in green within 3s.

- [ ] **Step 4: Have the other side speak a sentence**

Expected: line appears as `[Eles]` in blue within 3s.

- [ ] **Step 5: Have the other side ask "qual sua experiência com python?"**

Expected: card appears within 2-3s, classified Personal or Hybrid, with a sensible answer.

- [ ] **Step 6: Share screen on Teams showing this window**

Expected: other participant **does not see** the window in the shared screen — they see your desktop wallpaper or whatever is behind it.

- [ ] **Step 7: Press Ctrl+Win briefly while in another window and dictate**

Expected: dictation still works, text pasted, no interference with the meeting capture.

- [ ] **Step 8: Click "Parar reunião"**

Expected: window closes, files appear in `reunioes/<timestamp>/transcript.txt` and `sumario.md`.

- [ ] **Step 9: Review files**

Expected: transcript matches what was said; summary makes sense (or shows fallback message if Groq failed).

- [ ] **Step 10: Document any failures in `reunioes/<timestamp>/issues.md` for follow-up**

- [ ] **Step 11: If all green, commit a smoke-test report (optional)**

```bash
git add reunioes/.smoke-passed-2026-04-29.md  # write a brief PASS summary if you want a record
git commit -m "test(meeting): manual e2e smoke pass"
```

---

### Task 30: Final pass — gitignore review and commit polish

**Files:**
- Modify (if needed): `.gitignore`

- [ ] **Step 1: Confirm new artifacts are ignored**

Run:
```bash
git status --ignored | head -30
```

Expected: `reunioes/`, `knowledge/.index.npz`, `meeting/.window_state.json`, `models/llm/` listed as ignored.

- [ ] **Step 2: If anything sensitive is staged, fix `.gitignore` and unstage**

If you find `*.token`, real `perfil.md` content, or any reunião in staging, add to `.gitignore` and:

```bash
git rm --cached <path>
git add .gitignore
git commit -m "chore: tighten gitignore for meeting artifacts"
```

- [ ] **Step 3: Push everything**

```bash
git push origin main
```

Expected: success.

---

## Done

- All 30 tasks completed
- All unit tests passing (`pytest tests/meeting/ -v`)
- Manual smoke test passed
- Pushed to GitHub

This plan implements the full spec at `docs/superpowers/specs/2026-04-28-meeting-mode-design.md`. Future v2 items (speaker diarization, edição inline, tradução, integração mobile) ficam fora desta entrega.
