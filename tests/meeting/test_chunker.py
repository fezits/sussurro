from meeting.intelligence.rag.chunker import chunk_text


def test_chunker_returns_overlapping_chunks_close_to_size():
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    assert len(chunks) > 1
    assert all(50 <= len(c.split()) <= 110 for c in chunks)


def test_chunker_short_input_one_chunk():
    chunks = chunk_text("hello world", chunk_size=100, overlap=10)
    assert chunks == ["hello world"]
