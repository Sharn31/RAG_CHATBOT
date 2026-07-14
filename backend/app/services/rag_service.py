"""Orchestrates the end-to-end RAG pipeline. This is the only module that
routers should call into directly - it composes the lower-level services so
`api/upload.py` and `api/chat.py` stay thin.
"""

from typing import List

from app.config import settings
from app.schemas.response import UploadResponse, ChatResponse, SourceChunk
from app.services import pdf_service, chunk_service, embedding_service, vector_service, llm_service, memory_service
from app.utils.helpers import generate_session_id, truncate_snippet, dedupe_sources_by_page
from app.utils.prompt import NOT_FOUND_TOKEN


def ingest_pdf(pdf_path: str, filename: str) -> UploadResponse:
    """Full ingestion pipeline: extract -> chunk -> embed -> index -> register session."""
    pages = pdf_service.extract_pages(pdf_path)
    if not pages:
        raise ValueError("No extractable text found in PDF (it may be scanned/image-only).")

    chunks = chunk_service.build_chunks(pages)
    if not chunks:
        raise ValueError("PDF text could not be split into chunks.")

    session_id = generate_session_id()
    chunk_service.cache_chunks(session_id, filename, chunks)

    texts = [c["text"] for c in chunks]
    embeddings = embedding_service.embed_texts(texts)
    embedding_service.cache_embeddings(session_id, embeddings)

    store = vector_service.get_vector_store()
    store.create_session_collection(session_id, chunks, embeddings)

    memory = memory_service.get_memory_service()
    memory.create_session(session_id, filename, len(pages))

    return UploadResponse(
        session_id=session_id,
        filename=filename,
        num_pages=len(pages),
        num_chunks=len(chunks),
    )


def answer_question(session_id: str, question: str) -> ChatResponse:
    """Full query pipeline: retrieve -> gate on similarity -> ask LLM -> gate on NOT_FOUND -> respond."""
    memory = memory_service.get_memory_service()
    if not memory.exists(session_id):
        raise LookupError("Session not found. Upload a PDF first.")

    store = vector_service.get_vector_store()
    #query_embedding = embedding_service.embed_query(question)
    history = memory.get_history(session_id)

    recent_history = history[-4:]  # last 4 messages

    context = "\n".join(
    f"{m['role']}: {m['content']}"
    for m in recent_history
    )

    search_query = f"""
    Conversation:
    {context}

    Current Question:
    {question}
    """

    query_embedding = embedding_service.embed_query(search_query)
    retrieved = store.query_session(session_id, query_embedding, settings.TOP_K)

    # Layer 1: retrieval-based gate. If nothing is close enough, skip the LLM entirely.
    if not retrieved or retrieved[0]["distance"] > settings.SIMILARITY_THRESHOLD:
        return ChatResponse(answer=settings.OUT_OF_SCOPE_MESSAGE, sources=[], in_scope=False)

    history = memory.get_history(session_id)
    raw_answer = llm_service.generate_answer(question, retrieved, history)

    # Layer 2: LLM-based gate. The LLM itself confirms the context doesn't answer it.
    if NOT_FOUND_TOKEN in raw_answer:
        return ChatResponse(answer=settings.OUT_OF_SCOPE_MESSAGE, sources=[], in_scope=False)

    memory.append_turn(session_id, "user", question)
    memory.append_turn(session_id, "assistant", raw_answer)

    sources: List[SourceChunk] = [
        SourceChunk(page=c["page"], snippet=truncate_snippet(c["text"])) for c in retrieved
    ]
    sources = dedupe_sources_by_page(sources)

    return ChatResponse(answer=raw_answer, sources=sources, in_scope=True)


def delete_session(session_id: str) -> None:
    vector_service.get_vector_store().delete_session(session_id)
    memory_service.get_memory_service().delete(session_id)
