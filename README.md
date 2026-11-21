# AI Knowledge Inbox

React frontend, FastAPI backend, SQLite ingestion, Ollama embeddings, background indexing, semantic search, and cited local LLM answers.

## Embeddings and search

Copy `backend/.env.example` to `backend/.env` and restart the backend. Ollama must be running with `embeddinggemma` and `qwen2.5:1.5b` installed. New content indexes automatically; existing items have an Index content button. No API key or paid service is required.

Chunks contain up to 1,200 characters with 200-character overlap, preferring newline/word boundaries in the latter half. This intentionally uses characters, not token estimates: it is dependency-free, keeps multilingual chunks bounded, and retains nearby context. Chunks, normalized vectors, model IDs, and source relationships persist in SQLite. Index replacement is transactional. Failures preserve raw content and expose a retry action. Restart-interrupted jobs are marked failed; use a durable queue for production. Run a single backend process with this lightweight worker design.

`POST /search` accepts `{"question":"support hours","top_k":5}` and returns ranked snippets with source IDs and URLs. `POST /query` performs the same retrieval, then asks the local chat model to answer from those snippets and returns the cited source records. It scans vectors for the current model and uses cosine similarity. Scores are rankings, not confidence probabilities. Model changes require reindexing. Empty indexes return no results without making an API call. At scale, replace the linear scan with indexed vector search and paginate summary records instead of full content.

Indexing caps items at 500 chunks and batches API requests in groups of 32. No placeholder vectors are used in the running app. Controlled vectors are used only in tests. Run `.venv\Scripts\python.exe -m unittest test_search test_urls` for deterministic checks; real semantic quality requires a configured provider and representative questions.

## URL imports

Send `POST /ingest` with `{"type":"url","url":"https://example.com"}`. The backend fetches HTML/plain text, extracts readable text, and stores the original response text, original URL, final URL, title, and timestamp. Existing note databases are migrated automatically without deleting data.

Only public HTTP/HTTPS destinations on ports 80/443 are accepted. DNS addresses are checked and pinned for the connection; redirects are revalidated. TLS certificate verification is enabled. Imports are limited to 2 MB, three redirects, eight seconds per socket operation and a 25-second fetch budget (OS DNS resolution can exceed this budget). Unsupported formats, empty pages, and failed fetches return descriptive errors. Compressed responses are rejected; requests ask for identity encoding.

Extraction is deliberately basic: scripts, styles, navigation, and common page furniture are removed. There is no browser rendering, login support, or PDF import. Ingestion runs in a synchronous FastAPI worker thread, with an importing state in the UI; durable background jobs are future work. Raw HTML is never rendered in the frontend.

Verification (Windows): run `.venv\Scripts\python.exe -m unittest test_search test_urls` and `.venv\Scripts\python.exe verify_notes.py` from backend. Integration checks use a temporary database and port 18001.

## Notes API

- `POST /ingest`: JSON `{"type":"note","content":"Your note"}`; returns the saved item with HTTP 201.
- `GET /items?limit=20&offset=0`: returns `items` and `total`, newest first. Maximum limit: 100.
- Notes must contain non-whitespace text and cannot exceed 20,000 characters. Invalid inputs return HTTP 422.
- Raw text is preserved, with a UTC timestamp, UUID, source type, and processing status. Status moves through `saved`, `indexing`, `ready`, or `failed`.
- SQLite is created automatically at `backend/data/inbox.db`. Set `INBOX_DB_PATH` to override it.
- Structured request logs include request IDs, status, and duration without note bodies. Database errors return HTTP 503.

## Backend (PowerShell)

From the project directory:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

If recreating the virtual environment, run `python -m venv .venv` using a working Python installation first.

API health: http://127.0.0.1:8000/health
API documentation: http://127.0.0.1:8000/docs

## Frontend (another PowerShell terminal)

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173 to save notes and view the saved-items list.
Vite proxies `/api` requests to FastAPI on port 8000 during development.
`npm run build` verifies the production frontend build. Production deployment will need its own API reverse proxy configuration.

## Local AI setup

No paid API credentials are required. Install Ollama, start it, and download the local models:

```powershell
ollama pull embeddinggemma
ollama pull qwen2.5:1.5b
```

Ollama must be running at `http://127.0.0.1:11434`. Copy `backend/.env.example` to `backend/.env`, then restart FastAPI after changing model settings.

XAMPP/Apache is not needed. Never commit `.env` files or API keys.
