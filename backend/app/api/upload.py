"""PDF upload endpoint - extracts, chunks, embeds, and indexes the document,
returning a session_id used by /chat for all follow-up questions.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from app.config import Settings
from app.dependencies import get_settings
from app.schemas.response import UploadResponse
from app.services import rag_service
from app.utils.pdf_utils import validate_pdf_extension, save_upload_file

router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    if not validate_pdf_extension(file.filename):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    dest_path = save_upload_file(file, settings.UPLOAD_DIR)

    try:
        return rag_service.ingest_pdf(dest_path, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {e}")
