"""
Memory Service - Manages conversation history and session metadata.

Features:
- Session creation and management
- Conversation history tracking
- Document metadata storage (document type, extracted entities)
- Persistence to disk (JSON)
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class MemoryService:
    """
    Manages conversation history and session data.

    Each session stores:
    - filename: Name of uploaded document
    - created_at: Timestamp when session was created
    - history: List of conversation turns (user/assistant messages)
    - metadata: Document type, extracted entities, etc.
    """

    def __init__(self, history_path: str = "app/conversation/history.json"):
        """
        Initialize MemoryService.

        Args:
            history_path: Path to store conversation history JSON file
        """
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._load_all_sessions()

    # ========================================================================
    # Session Management
    # ========================================================================

    def create_session(
        self,
        session_id: str,
        filename: str,
        num_pages: int
    ) -> None:
        """
        Create a new session for a document.

        Args:
            session_id: Unique session identifier
            filename: Name of uploaded file
            num_pages: Number of pages in document
        """
        self.sessions[session_id] = {
            "session_id": session_id,
            "filename": filename,
            "num_pages": num_pages,
            "created_at": datetime.now().isoformat(),
            "history": [],
            "metadata": {},
        }
        self._persist_session(session_id)
        print(f"✅ Session created: {session_id}")

    def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        return session_id in self.sessions

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Backward-compatible accessor: returns the full raw session dict
        (session_id, filename, num_pages, created_at, history, metadata),
        or None if the session doesn't exist. Used by routes that need the
        raw session (e.g. GET /session/{id}) rather than the trimmed view
        from get_session_info().
        """
        return self.sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        """Delete a session and its history."""
        if session_id in self.sessions:
            del self.sessions[session_id]

            # Delete from disk
            session_file = self.history_path.parent / f"{session_id}.json"
            if session_file.exists():
                session_file.unlink()

            print(f"✅ Session deleted: {session_id}")

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get basic session information.

        Returns:
            Dict with session_id, filename, num_pages, created_at
        """
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        return {
            "session_id": session["session_id"],
            "filename": session["filename"],
            "num_pages": session.get("num_pages", 0),
            "created_at": session["created_at"],
        }

    # ========================================================================
    # Conversation History
    # ========================================================================

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> None:
        """
        Add a message to conversation history.

        Args:
            session_id: Session identifier
            role: "user" or "assistant"
            content: Message content
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        self.sessions[session_id]["history"].append({
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content,
        })

        self._persist_session(session_id)

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get full conversation history for a session.

        Returns:
            List of messages: [{"timestamp": "...", "role": "user/assistant", "content": "..."}]
        """
        if session_id not in self.sessions:
            return []

        return self.sessions[session_id].get("history", [])

    def get_recent_history(
        self,
        session_id: str,
        max_turns: int = 4
    ) -> List[Dict[str, str]]:
        """
        Get recent conversation history (last N turns).

        Args:
            session_id: Session identifier
            max_turns: Maximum number of recent turns to return

        Returns:
            List of recent messages
        """
        history = self.get_history(session_id)
        return history[-max_turns:] if history else []

    def clear_history(self, session_id: str) -> None:
        """Clear all conversation history for a session."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        self.sessions[session_id]["history"] = []
        self._persist_session(session_id)

    # ========================================================================
    # Metadata Management
    # ========================================================================

    def set_metadata(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """
        Store document metadata (document type, entities, etc.).

        Args:
            session_id: Session identifier
            metadata: Dictionary with metadata

        Example:
            memory.set_metadata(session_id, {
                "document_type": "resume",
                "entities": {
                    "name": "Dilkash Singh",
                    "email": "dilkash@example.com",
                    "phone": "+1-555-1234"
                }
            })
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        self.sessions[session_id]["metadata"] = metadata
        self._persist_session(session_id)
        print(f"✅ Metadata stored for session {session_id}")

    def get_metadata(self, session_id: str) -> Dict[str, Any]:
        """
        Retrieve document metadata for a session.

        Returns:
            Metadata dictionary or empty dict if not found
        """
        if session_id not in self.sessions:
            return {}

        return self.sessions[session_id].get("metadata", {})

    def update_metadata(self, session_id: str, key: str, value: Any) -> None:
        """
        Update a specific metadata field.

        Args:
            session_id: Session identifier
            key: Metadata key (e.g., "document_type")
            value: Metadata value
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        if "metadata" not in self.sessions[session_id]:
            self.sessions[session_id]["metadata"] = {}

        self.sessions[session_id]["metadata"][key] = value
        self._persist_session(session_id)

    # ========================================================================
    # Persistence
    # ========================================================================

    def _persist_session(self, session_id: str) -> None:
        """
        Save a session to disk (JSON file).

        Args:
            session_id: Session identifier
        """
        if session_id not in self.sessions:
            return

        try:
            session_file = self.history_path.parent / f"{session_id}.json"

            # encoding='utf-8' is required: resume/document text can contain
            # emoji or other non-ASCII characters (e.g. 📍 ✉️ 🌐 in contact
            # info). Without an explicit encoding, Windows defaults to the
            # system codepage (often cp1252 / "charmap"), which can't
            # represent those characters and either fails to write or writes
            # a corrupted file that then fails to read back on startup.
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions[session_id], f, indent=2, ensure_ascii=False)

            print(f"💾 Session persisted: {session_file}")
        except Exception as e:
            print(f"⚠️  Failed to persist session {session_id}: {str(e)}")

    def _load_all_sessions(self) -> None:
        """Load all sessions from disk on startup."""
        history_dir = self.history_path.parent
        history_dir.mkdir(parents=True, exist_ok=True)

        for session_file in history_dir.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    session_id = session_data.get("session_id")
                    if session_id:
                        self.sessions[session_id] = session_data
                        print(f"📂 Loaded session: {session_id}")
            except Exception as e:
                print(f"⚠️  Failed to load {session_file}: {str(e)}")

    def _load_session(self, session_id: str) -> bool:
        """
        Load a specific session from disk.

        Args:
            session_id: Session identifier

        Returns:
            True if loaded successfully, False otherwise
        """
        session_file = self.history_path.parent / f"{session_id}.json"

        if not session_file.exists():
            return False

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                self.sessions[session_id] = json.load(f)
            return True
        except Exception as e:
            print(f"⚠️  Failed to load session {session_id}: {str(e)}")
            return False

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get info about all sessions."""
        return [
            self.get_session_info(session_id)
            for session_id in self.sessions.keys()
        ]

    def get_conversation_count(self, session_id: str) -> int:
        """Get total number of turns in conversation."""
        return len(self.get_history(session_id))

    def export_session(self, session_id: str) -> Dict[str, Any]:
        """
        Export full session data (for backup/analysis).

        Returns:
            Complete session dictionary
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        return self.sessions[session_id].copy()


# ============================================================================
# Global Instance & Singleton Pattern
# ============================================================================

_memory_service_instance: Optional[MemoryService] = None


def get_memory_service(history_path: str = "app/conversation/history.json") -> MemoryService:
    """
    Get or create the global MemoryService instance.

    This follows the singleton pattern to ensure only one instance
    manages all conversation history.

    Args:
        history_path: Path to history file (used on first call)

    Returns:
        MemoryService singleton instance

    Usage:
        memory = get_memory_service()
        memory.create_session("abc123", "resume.pdf", 1)
    """
    global _memory_service_instance

    if _memory_service_instance is None:
        _memory_service_instance = MemoryService(history_path)

    return _memory_service_instance


def reset_memory_service() -> None:
    """Reset the memory service (mainly for testing)."""
    global _memory_service_instance
    _memory_service_instance = None


# ============================================================================
# Testing & Debugging
# ============================================================================

if __name__ == "__main__":
    # Quick test
    print("Testing MemoryService...\n")

    memory = get_memory_service()

    # Create session
    session_id = str(uuid.uuid4())
    memory.create_session(session_id, "test_resume.pdf", 1)

    # Add metadata
    memory.set_metadata(session_id, {
        "document_type": "resume",
        "entities": {
            "name": "Test User",
            "email": "test@example.com",
        }
    })

    # Add conversation turns
    memory.append_turn(session_id, "user", "What is my name?")
    memory.append_turn(session_id, "assistant", "Your name is Test User")

    # Retrieve data
    print(f"\nSession Info:")
    print(json.dumps(memory.get_session_info(session_id), indent=2))

    print(f"\nMetadata:")
    print(json.dumps(memory.get_metadata(session_id), indent=2))

    print(f"\nHistory ({memory.get_conversation_count(session_id)} turns):")
    for msg in memory.get_history(session_id):
        print(f"  {msg['role']}: {msg['content']}")

    print("\n✅ MemoryService test complete!")