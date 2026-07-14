"""Thin wrapper around any OpenAI-compatible chat completion API
(OpenAI, Groq, OpenRouter, Ollama's OpenAI-compatible proxy, etc.),
selected entirely via LLM_BASE_URL / LLM_MODEL / LLM_API_KEY in .env.
"""

from typing import List, Dict
from openai import OpenAI

from app.config import settings
from app.utils.prompt import SYSTEM_PROMPT, build_user_message

_client: OpenAI = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
    return _client


def generate_answer(question: str, chunks: List[Dict], history: List[Dict]) -> str:
    """Calls the LLM with the retrieved context and recent conversation history.

    history: [{"role": "user"/"assistant", "content": str}, ...], oldest first.
    Returns the raw completion text, which may be the NOT_FOUND_TOKEN
    defined in app.utils.prompt.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-(settings.MAX_HISTORY_TURNS * 2):])
    messages.append({"role": "user", "content": build_user_message(question, chunks)})

    client = get_client()
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=0.1,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()
