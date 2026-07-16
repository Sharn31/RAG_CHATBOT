# 

#new 
"""Thin wrapper around any OpenAI-compatible chat completion API
(OpenAI, Groq, OpenRouter, Ollama's OpenAI-compatible proxy, etc.),
selected entirely via LLM_BASE_URL / LLM_MODEL / LLM_API_KEY in .env.
"""

import time
from typing import List, Dict
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, APIStatusError

from app.config import settings
from app.utils.prompt import SYSTEM_PROMPT, build_user_message

_client: OpenAI = None

# Tunable without touching .env - bump these if your provider is
# consistently slow rather than actually down.
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.5  # doubles each retry: 1.5s, 3s, 6s


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    return _client


def generate_answer(question: str, chunks: List[Dict], history: List[Dict]) -> str:
    """Calls the LLM with the retrieved context and recent conversation history.

    history: [{"role": "user"/"assistant", "content": str}, ...], oldest first.
    Returns the raw completion text, which may be the NOT_FOUND_TOKEN
    defined in app.utils.prompt.

    Raises RuntimeError with a clear, user-facing message if the provider
    is unreachable/rate-limited/timing out after retries - callers (chat.py)
    should catch this and return it as the answer rather than a raw 500,
    so a flaky provider doesn't crash the whole request.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-(settings.MAX_HISTORY_TURNS * 2):])
    messages.append({"role": "user", "content": build_user_message(question, chunks)})

    client = get_client()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=800,
            )
            return response.choices[0].message.content.strip()

        except RateLimitError as e:
            last_error = e
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"[llm_service] Rate limited (attempt {attempt}/{MAX_RETRIES}), retrying in {wait:.1f}s")
            time.sleep(wait)

        except (APITimeoutError, APIConnectionError) as e:
            last_error = e
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"[llm_service] {type(e).__name__} (attempt {attempt}/{MAX_RETRIES}), retrying in {wait:.1f}s")
            time.sleep(wait)

        except APIStatusError as e:
            # 4xx/5xx from the provider that isn't rate-limiting (e.g. bad
            # API key, invalid model name) - retrying won't help, fail fast
            # with a message that actually points at the real problem.
            print(f"[llm_service] Provider returned status {e.status_code}: {e.message}")
            raise RuntimeError(
                f"The LLM provider rejected the request (status {e.status_code}). "
                f"Check LLM_API_KEY / LLM_MODEL / LLM_BASE_URL in your .env."
            ) from e

    print(f"[llm_service] Giving up after {MAX_RETRIES} attempts: {last_error}")
    raise RuntimeError(
        "The LLM provider is currently unreachable or rate-limiting requests. "
        "Please try again in a moment."
    ) from last_error