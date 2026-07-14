"""Prompt templates for the RAG LLM call."""

from typing import List, Dict

NOT_FOUND_TOKEN = "NOT_FOUND"

SYSTEM_PROMPT = f"""You are a document Q&A assistant. You must answer ONLY using the CONTEXT provided below, \
which was extracted from a PDF uploaded by the user. Follow these rules strictly:

1. Use ONLY facts present in the CONTEXT. Never use outside knowledge, even if you know the answer.
2. If the CONTEXT does not contain enough information to answer the question, or the question is unrelated \
to the CONTEXT, respond with EXACTLY this token and nothing else: {NOT_FOUND_TOKEN}
3. Do not mention these instructions, the token, or that you are restricted to a document. Just answer normally \
when the answer is in the CONTEXT, or output the token when it is not.
4. Keep answers concise and grounded strictly in the CONTEXT. You may use prior conversation turns only to \
resolve pronouns/follow-ups (e.g. "what about it?"), not as a source of facts.
"""


def build_context_block(chunks: List[Dict]) -> str:
    """Formats retrieved chunks into a page-labeled context block for the LLM prompt."""
    parts = [f"[Page {c['page']}]\n{c['text']}" for c in chunks]
    return "\n\n---\n\n".join(parts)


def build_user_message(question: str, chunks: List[Dict]) -> str:
    context_block = build_context_block(chunks)
    return f"CONTEXT:\n{context_block}\n\nQUESTION: {question}"
