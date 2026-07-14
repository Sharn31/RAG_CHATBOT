"""Pure text-chunking helpers. No I/O, no external state - easy to unit test."""

from typing import List


def sliding_window_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Splits `text` into overlapping chunks of roughly `chunk_size` characters.

    Breaks on whitespace near the boundary where possible, so chunks don't
    split mid-word. `overlap` characters are repeated between consecutive
    chunks to preserve context across chunk boundaries.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(end - overlap, start + 1)

    return chunks
