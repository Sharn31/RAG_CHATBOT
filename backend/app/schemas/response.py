from pydantic import BaseModel
from typing import List, Optional


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    num_pages: int
    num_chunks: int


class SourceChunk(BaseModel):
    page: int
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceChunk] = []
    in_scope: bool


class SessionInfo(BaseModel):
    session_id: str
    filename: Optional[str] = None
    num_pages: Optional[int] = None
    turns: int = 0


class HealthResponse(BaseModel):
    status: str
