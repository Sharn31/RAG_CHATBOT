

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session ID returned by /upload")
    question: str = Field(..., min_length=1, description="User's question about the uploaded PDF")
