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
