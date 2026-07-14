# Folio — Frontend

Single HTML file, no build step, no dependencies besides two Google Fonts
(loaded from a CDN link in the `<head>`).

## Run it

Just open `index.html` in a browser, or serve the folder with any static
server, e.g.:

```bash
python -m http.server 5500
```

## Connecting to your backend

The frontend calls three endpoints as relative paths:

```
POST /upload
POST /chat
GET  /session/{id}
DELETE /session/{id}
```

**If you serve this file from the same FastAPI app as the backend** (e.g. as
`app/static/index.html`, mounted at `/`), no changes are needed — the
relative paths resolve correctly on their own.

**If you're hosting this file separately** from the API (different port,
different domain, static host, etc.), open `index.html` and change this one
line near the top of the `<script>` block:

```js
const API = '';
```

to your backend's full URL, e.g.:

```js
const API = 'http://127.0.0.1:8000';
```

or in production:

```js
const API = 'https://your-api-domain.com';
```

Also make sure your backend's CORS settings allow requests from wherever
this file is hosted (the FastAPI backend already has `CORSMiddleware` with
`allow_origins=["*"]`, so this works out of the box against it).

## Expected API contract

**POST /upload** (multipart form, field name `file`) →
```json
{ "session_id": "...", "filename": "...", "num_pages": 3, "num_chunks": 12 }
```

**POST /chat** (JSON body `{ "session_id": "...", "question": "..." }`) →
```json
{
  "answer": "...",
  "sources": [ { "page": 4, "snippet": "..." } ],
  "in_scope": true
}
```

**GET /session/{id}** →
```json
{ "session_id": "...", "filename": "...", "num_pages": 3, "turns": 2 }
```

**DELETE /session/{id}** → `{ "status": "deleted" }`

If your backend's response shape differs, the fields to adjust are in the
`addAssistantMessage()`, `enterDocState()`, and `restoreSession()` functions
near the bottom of the file.
