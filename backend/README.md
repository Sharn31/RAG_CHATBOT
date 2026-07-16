# PDF RAG Chatbot

A Retrieval-Augmented Generation (RAG) chatbot that answers questions **only** from an uploaded PDF using ChromaDB, Sentence Transformers, and any OpenAI-compatible LLM.

## Features

- Upload PDF documents
- Semantic retrieval with Sentence Transformers
- ChromaDB vector database
- OpenAI / Groq / OpenRouter / Ollama support
- Conversation memory
- Page-number citations
- Out-of-scope detection
- FastAPI backend
- uv dependency management

## Project Structure

```text
backend/
├── main.py
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── services/
│   │   ├── pdf_service.py
│   │   ├── chunk_service.py
│   │   ├── embedding_service.py
│   │   ├── vector_service.py
│   │   ├── rag_service.py
│   │   ├── llm_service.py
│   │   └── memory_service.py
│   ├── utils/
│   └── uploads/
├── data/
├── .env
├── pyproject.toml
├── uv.lock
└── .python-version
```

## Architecture

```text
PDF
 │
 ▼
PyMuPDF
 │
 ▼
Chunking
 │
 ▼
Sentence Transformers
 │
 ▼
ChromaDB
 │
 ▼
Retriever
 │
 ▼
LLM
 │
 ▼
Answer + Sources
```



## Installation

### Clone

```bash
git clone https://github.com/Sharn31/RAG_CHATBOT.git
cd pdf-rag-chatbot/backend
```

### Install uv

Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Linux/macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify

```bash
uv --version
```


### Install all project dependencies from `pyproject.toml` and `uv.lock`:

```bash
uv sync
```
### Create virtual environment

```bash
uv venv
```

Windows

```bash
.venv\Scripts\activate
```

Linux/macOS

```bash
source .venv/bin/activate
```

### Install dependencies

```bash
uv sync
```

## Environment

Create `.env`

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile


EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

CHUNK_SIZE=800
CHUNK_OVERLAP=120

TOP_K=3
SIMILARITY_THRESHOLD=0.75
MAX_HISTORY_TURNS=5

HOST=127.0.0.1
PORT=8000
RELOAD=True
```

## Run

```bash
python main.py
```

or

```bash
uv run uvicorn app.main:app --reload
```

Swagger:

```
http://127.0.0.1:8000/docs
```
frontend : python -m http.server 5500
```
http://localhost:5500/
```


## API

| Method | Endpoint | Description |
|---|---|---|
| POST | /upload | Upload PDF |
| POST | /chat | Ask question |
| GET | /session/{id} | Session info |
| DELETE | /session/{id} | Delete session |
| GET | /health | Health |

## Workflow

1. Upload PDF.
2. Extract page text.
3. Chunk with overlap.
4. Generate embeddings.
5. Store in ChromaDB.
6. Retrieve Top-K chunks.
7. Send context to LLM.
8. Return answer and page sources.

Out-of-scope response:

> This question is outside the scope of the uploaded document. Please ask questions related to the uploaded PDF only.

## Frontend

If hosted separately:

```javascript
const API = "http://127.0.0.1:8000";
```

## Export requirements.txt

```bash
uv pip freeze > requirements.txt
```


