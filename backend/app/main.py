"""FastAPI application factory. Run via `python run.py` or `uvicorn app.main:app`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import upload, chat, health

app = FastAPI(
    title="PDF RAG Chatbot",
    description="Answers questions only from an uploaded PDF, using RAG with page-numbered sources.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(upload.router)
app.include_router(chat.router)
