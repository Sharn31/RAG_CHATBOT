"""Session registry + conversation history.

Holds, per session_id: uploaded filename, page count, and turn-by-turn chat
history. Kept in memory for speed, persisted to CONVERSATION_HISTORY_PATH
(a single JSON file keyed by session_id) so history survives a server restart.

"""

import json
import os
import threading
from typing import Dict, List, Optional

from app.config import settings

_lock = threading.Lock()


class MemoryService:
    def __init__(self, path: str):
        self._path = path
        self._sessions: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._sessions = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._sessions = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._sessions, f, ensure_ascii=False, indent=2)

    def create_session(self, session_id: str, filename: str, num_pages: int) -> None:
        with _lock:
            self._sessions[session_id] = {
                "filename": filename,
                "num_pages": num_pages,
                "history": [],
            }
            self._save()

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def get(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def get_history(self, session_id: str) -> List[dict]:
        s = self._sessions.get(session_id)
        return s["history"] if s else []

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        with _lock:
            if session_id in self._sessions:
                self._sessions[session_id]["history"].append({"role": role, "content": content})
                self._save()

    def delete(self, session_id: str) -> None:
        with _lock:
            self._sessions.pop(session_id, None)
            self._save()


_memory_instance = None


def get_memory_service() -> MemoryService:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = MemoryService(settings.CONVERSATION_HISTORY_PATH)
    return _memory_instance
