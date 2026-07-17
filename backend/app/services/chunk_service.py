
"""Splits extracted page text into page-tagged chunks, and caches the result
to `data/processed/`. Originally written purely for debugging/inspection,
but get_cached_chunks() below is now a real dependency: rag_service's
ExperienceCalculator fast path needs the full chunk set (not just the
top-TOP_K retrieved by the vector store) to reliably find every date range
in the document, so it reads this cache back rather than re-extracting the
PDF on every "total experience" question.
"""

import os
import json
from typing import List, Tuple, Dict

from app.config import settings
from app.utils.chunk_utils import sliding_window_chunks


def build_chunks(pages: List[Tuple[int, str]]) -> List[Dict]:
    """pages: [(page_number, text), ...] -> [{"text": str, "page": int}, ...]

    Chunking is done per-page so every chunk can be tagged with an accurate
    page number for citation in the final answer.
    """
    chunks = []
    for page_num, text in pages:
        for piece in sliding_window_chunks(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP):
            chunks.append({"text": piece, "page": page_num})
    return chunks


def cache_chunks(session_id: str, filename: str, chunks: List[Dict]) -> None:
    """Writes chunks + metadata to data/processed/{session_id}_*.json."""
    os.makedirs(settings.PROCESSED_DATA_DIR, exist_ok=True)

    chunks_path = os.path.join(settings.PROCESSED_DATA_DIR, f"{session_id}_chunks.json")
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    metadata_path = os.path.join(settings.PROCESSED_DATA_DIR, f"{session_id}_metadata.json")
    metadata = {
        "session_id": session_id,
        "filename": filename,
        "num_chunks": len(chunks),
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def get_cached_chunks(session_id: str) -> List[Dict]:
    """Reads back the full chunk list written by cache_chunks() for a
    session. Returns [] if the cache file is missing (e.g. it was manually
    cleared, or PROCESSED_DATA_DIR was wiped) rather than raising, since
    callers (e.g. ExperienceCalculator) are expected to treat "no chunks
    found" as "fall through to normal retrieval" rather than a hard failure.
    """
    chunks_path = os.path.join(settings.PROCESSED_DATA_DIR, f"{session_id}_chunks.json")
    if not os.path.exists(chunks_path):
        return []
    try:
        with open(chunks_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []