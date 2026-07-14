"""Low-level filesystem helpers for handling uploaded PDF files."""

import os
import shutil
from fastapi import UploadFile


def validate_pdf_extension(filename: str) -> bool:
    """Returns True if the filename has a .pdf extension (case-insensitive)."""
    return bool(filename) and filename.lower().endswith(".pdf")


def save_upload_file(upload_file: UploadFile, dest_dir: str) -> str:
    """Persists an UploadFile to dest_dir and returns the saved path.

    Note: uploads are saved by original filename. In a multi-user production
    deployment, prefix with a session/UUID to avoid collisions between users
    uploading files with the same name.
    """
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, upload_file.filename)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(upload_file.file, f)
    return dest_path
