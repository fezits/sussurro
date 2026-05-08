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
