"""Small generic helpers shared across services."""

import uuid
from typing import List
from app.schemas.response import SourceChunk


def generate_session_id() -> str:
    return str(uuid.uuid4())


def truncate_snippet(text: str, max_len: int = 180) -> str:
    text = text.strip()
    return text if len(text) <= max_len else text[:max_len].rstrip() + "..."


def dedupe_sources_by_page(sources: List[SourceChunk]) -> List[SourceChunk]:
    """Removes duplicate page numbers while preserving relevance order."""
    seen = set()
    result = []
    for s in sources:
        if s.page not in seen:
            seen.add(s.page)
            result.append(s)
    return result
