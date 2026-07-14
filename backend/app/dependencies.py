"""Shared FastAPI dependencies, injected into routers via Depends()."""

from app.config import Settings, settings as _settings
from app.services.memory_service import MemoryService, get_memory_service as _get_memory_service


def get_settings() -> Settings:
    return _settings


def get_memory_service() -> MemoryService:
    return _get_memory_service()
