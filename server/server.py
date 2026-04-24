from __future__ import annotations

import io
import secrets
import socket
import sys
import time
import wave
from pathlib import Path

import numpy as np
import yaml
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.transcriber import Transcriber

SERVER_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SERVER_DIR / "server_token.txt"
CONFIG_FILE = SERVER_DIR / "server.yaml"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_or_create_token() -> str:
    if TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if t:
            return t
    t = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(t, encoding="utf-8")
    return t


def get_local_ips() -> list[str]:
    ips: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def decode_audio(data: bytes) -> np.ndarray:
    """Decode WAV PCM16 or arbitrary media via pyav (same lib faster-whisper uses)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            if wf.getsampwidth() == 2 and wf.getframerate() in (16000, 44100, 48000):
                raw = wf.readframes(wf.getnframes())
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if wf.getnchannels() == 2:
                    audio = audio.reshape(-1, 2).mean(axis=1)
                if wf.getframerate() != 16000:
                    audio = _resample_to_16k(audio, wf.getframerate())
                return audio
    except (wave.Error, EOFError):
        pass

    import av  # noqa: WPS433

    container = av.open(io.BytesIO(data))
    try:
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.audio.resampler.AudioResampler(
            format="flt",
            layout="mono",
            rate=16000,
        )
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                arr = resampled.to_ndarray().reshape(-1).astype(np.float32)
                chunks.append(arr)
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)
    finally:
        container.close()


def _resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    if sr == 16000:
        return audio
    ratio = 16000 / sr
    new_len = int(round(len(audio) * ratio))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


config = load_config()
whisper_cfg = config.get("whisper", {})
server_cfg = config.get("server", {})

TOKEN = load_or_create_token()
HOST = server_cfg.get("host", "0.0.0.0")
PORT = int(server_cfg.get("port", 8765))

transcriber = Transcriber(
    model_size=whisper_cfg.get("model", "small"),
    language=whisper_cfg.get("language", "pt"),
    device=whisper_cfg.get("device", "auto"),
    compute_type=whisper_cfg.get("compute_type", "auto"),
    beam_size=int(whisper_cfg.get("beam_size", 1)),
    vad_filter=bool(whisper_cfg.get("vad_filter", True)),
    download_root=ROOT / whisper_cfg.get("model_dir", "models"),
)

app = FastAPI(title="Sussurro Server", version="1.0.0")


def require_token(authorization: str | None = Header(None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, TOKEN):
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "model": whisper_cfg.get("model", "small"),
            "device": transcriber.device,
        }
    )


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: str | None = Form(None),
    _=Depends(require_token),
):
    start = time.monotonic()
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    try:
        samples = decode_audio(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not decode audio: {e}") from e

    if samples.size == 0:
        return {"text": "", "ms": 0}

    original_language = transcriber.language
    if language:
        transcriber.language = language
    try:
        text = transcriber.transcribe(samples)
    finally:
        transcriber.language = original_language

    ms = int((time.monotonic() - start) * 1000)
    return {"text": text, "ms": ms, "audio_seconds": round(samples.size / 16000, 2)}


def print_banner() -> None:
    print()
    print("=" * 60)
    print(" SUSSURRO SERVER")
    print("=" * 60)
    print(f" Model      : {whisper_cfg.get('model', 'small')} ({transcriber.device})")
    print(f" Port       : {PORT}")
    print(f" Token      : {TOKEN}")
    print(f" Token file : {TOKEN_FILE}")
    print()
    print(" Reachable at:")
    for ip in get_local_ips():
        print(f"   http://{ip}:{PORT}")
    print()
    print(" Use the token above in the mobile app.")
    print("=" * 60)
    print()


def main() -> None:
    import uvicorn

    from server.discovery import MdnsBroadcaster

    print_banner()
    broadcaster = MdnsBroadcaster(port=PORT)
    try:
        broadcaster.start()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] mDNS broadcast not available: {e}")

    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="info")
    finally:
        broadcaster.stop()


if __name__ == "__main__":
    main()
