# PDF RAG Chatbot

Answers questions only from an uploaded PDF, with page-numbered sources, using
Retrieval-Augmented Generation (ChromaDB + Sentence Transformers) and any
OpenAI-compatible LLM (OpenAI, Groq, OpenRouter, Ollama, ...).

If a question can't be answered from the uploaded document, it responds with:

> This question is outside the scope of the uploaded document. Please ask
> questions related to the uploaded PDF only.

## Architecture

```
backend/
├── main.py                 Launcher - starts uvicorn with settings from .env
├── app/
│   ├── main.py              FastAPI app - wires routers together
│   ├── config.py            Settings (env-driven, single source of truth)
│   ├── dependencies.py      Shared FastAPI Depends() providers
│   │
│   ├── services/            Business logic
│   │   ├── pdf_service.py         PyMuPDF text extraction, per page
│   │   ├── chunk_service.py       Page-tagged chunking + debug cache
│   │   ├── embedding_service.py   sentence-transformers wrapper
│   │   ├── vector_service.py      ChromaDB storage/retrieval
│   │   ├── rag_service.py         Orchestrates the pipeline end to end
│   │   ├── llm_service.py         OpenAI-compatible chat completion call
│   │   └── memory_service.py      Session registry + conversation history
│   │
│   ├── utils/
│   │   ├── pdf_utils.py     Filesystem helpers for uploaded files
│   │   ├── chunk_utils.py   Pure sliding-window chunking function
│   │   ├── prompt.py        System prompt + NOT_FOUND token
│   │   └── helpers.py       Misc (session IDs, snippet truncation, dedupe)
│   │
│   └── uploads/              Saved PDF files
│
├── data/                    Debug caches (chunks/metadata/embeddings per session)
├── tests/                   Test suite
├── .env                     Configuration (see below)
├── .python-version
├── pyproject.toml
└── uv.lock
```

**Request flow:** routers call `rag_service` only; `rag_service` composes
`pdf_service` → `chunk_service` → `embedding_service` → `vector_service` →
`llm_service` / `memory_service`. No router talks to a low-level service
directly, which keeps the pipeline testable and swappable.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync
```

Then fill in your `.env` (see [Configuration](#configuration) below) — at
minimum, set `LLM_API_KEY`.

## Run

```bash
python main.py
```

or equivalently:

```bash
uv run uvicorn app.main:app --reload
```

By default this starts on `http://127.0.0.1:8000` (check `HOST` / `PORT` in
`.env` if you've changed them). API docs are available at
`http://127.0.0.1:8000/docs`.

## Test

```bash
uv run pytest tests/ -v
```

## How it works

1. **Upload** (`POST /upload`): `pdf_service` extracts text per page →
   `chunk_service` splits each page into overlapping chunks (tagging every
   chunk with its page number) → `embedding_service` embeds all chunks →
   `vector_service` indexes them under a fresh `session_id` →
   `memory_service` registers the session.
2. **Chat** (`POST /chat`): the question is embedded and matched against the
   session's vectors (top-`TOP_K`, cosine distance).
   - **Retrieval gate**: if the best match's distance exceeds
     `SIMILARITY_THRESHOLD`, the request is answered as out-of-scope without
     calling the LLM.
   - **LLM gate**: otherwise, the retrieved chunks + recent conversation
     history are sent to the LLM, instructed to answer only from context or
     emit a `NOT_FOUND` token if it can't.
   - Either gate returns the exact out-of-scope message shown above.
   - On success, `sources` lists the page numbers actually used, deduped and
     in relevance order.
3. **Follow-ups**: `memory_service` persists each session's conversation
   history, replayed to the LLM on each turn so it can resolve references
   like "what about that clause?".

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | Any OpenAI-compatible provider |
| `EMBEDDING_MODEL` | sentence-transformers model name |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Chunking granularity |
| `TOP_K` | Chunks retrieved per question |
| `SIMILARITY_THRESHOLD` | Retrieval gate strictness — cosine distance, lower = stricter. `all-MiniLM-L6-v2` is a general-purpose encoder, not fine-tuned for question↔passage matching, so 0.7–0.8 works better in practice than a naive 0.3–0.4 |
| `MAX_HISTORY_TURNS` | Conversation turns replayed to the LLM |
| `HOST` / `PORT` / `RELOAD` | Server settings used by `main.py` |

Provider examples:
```
OpenAI:      LLM_BASE_URL=https://api.openai.com/v1        LLM_MODEL=gpt-4o-mini
Groq:        LLM_BASE_URL=https://api.groq.com/openai/v1   LLM_MODEL=llama-3.3-70b-versatile
OpenRouter:  LLM_BASE_URL=https://openrouter.ai/api/v1     LLM_MODEL=meta-llama/llama-3.3-70b-instruct
Ollama:      LLM_BASE_URL=http://localhost:11434/v1        LLM_MODEL=llama3.1  (LLM_API_KEY=ollama)
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/upload` | Upload a PDF (multipart, field `file`), returns `session_id` |
| POST | `/chat` | `{session_id, question}` → `{answer, sources[], in_scope}` |
| GET | `/session/{id}` | Session metadata (filename, pages, turn count) |
| DELETE | `/session/{id}` | Clear a session + its vector index |
| GET | `/health` | Liveness check |

## Frontend

The frontend ("RAG CHATBOT") is a separate single-file HTML/CSS/JS app — no build
step. It calls the endpoints above as relative paths, so if you serve it
from this backend (e.g. `app/static/index.html` mounted at `/`) it works
with zero configuration. If hosted separately, set the `API` constant near
the top of its `<script>` block to this backend's URL, e.g.:

```js
const API = 'http://127.0.0.1:8000';
```

## Known limitations / next steps

- Scanned/image-only PDFs won't extract text - add OCR (`pytesseract`) if needed.
- Session/conversation state is kept in a single process - fine for local
  use or a single instance; swap for Redis/Postgres for multi-worker or
  high-concurrency deployments.
- ChromaDB runs in local persistent mode - fine for a single instance; use a
  hosted vector service for horizontal scaling.
- No auth - add an API key or session-ownership check before exposing publicly.