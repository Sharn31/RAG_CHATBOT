"""Ask-a-question endpoint, plus session inspection/cleanup endpoints."""

from fastapi import APIRouter, HTTPException, Depends

from app.dependencies import get_memory_service
from app.schemas.request import ChatRequest
from app.schemas.response import ChatResponse, SessionInfo
from app.services import rag_service
from app.services.memory_service import MemoryService

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        return rag_service.answer_question(req.session_id, req.question)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to answer question: {e}")


@router.get("/session/{session_id}", response_model=SessionInfo)
def get_session(session_id: str, memory: MemoryService = Depends(get_memory_service)):
    info = memory.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionInfo(
        session_id=info["session_id"],
        filename=info["filename"],
        num_pages=info["num_pages"],
        turns=memory.get_conversation_count(session_id) // 2,
    )


@router.delete("/session/{session_id}")
def delete_session(session_id: str, memory: MemoryService = Depends(get_memory_service)):
    if not memory.exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    rag_service.delete_session(session_id)
    return {"status": "deleted"}
