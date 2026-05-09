from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split into word-windowed chunks. chunk_size and overlap are in *words*.
    Tail slices smaller than (chunk_size - overlap) are dropped because their
    content is already covered by the previous chunk's overlap.
    """
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
        if len(slice_) < step and chunks:
            # Tail too small — already covered by previous chunk's overlap.
            break
        chunks.append(" ".join(slice_))
        i += step
    return chunks
