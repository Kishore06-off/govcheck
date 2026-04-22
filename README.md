# GovCheck AI — Governance document to checklist

GovCheck ingests governance and compliance documents (PDF, Word, Excel, CSV, text, and web URLs), chunks and embeds them, and produces structured checklist items using a **hybrid RAG** stack (ChromaDB dense search + BM25). Data is scoped by `user_id` so sessions stay isolated in the vector store and BM25 corpus.

---

## Architecture

| Layer | Role |
|--------|------|
| **FastAPI (`main.py`)** | REST API: upload jobs, status polling, chat/stream. Root `/` returns API status JSON. |
| **Streamlit (`app.py`)** | UI dashboard: upload/poll, checklist table, domain filters, CSV/JSON/Excel export, RAG chat tab. Calls the API via `API_URL` (default `http://localhost:8000`). |
| **Ingestion** | `ingestion/router.py` routes by file type or URL to loaders (PDF, DOCX, XLSX, CSV, scrape, etc.). |
| **Chunking** | `chunking/chunker.py` uses **embedding-based semantic chunking** (paragraph units + cosine similarity boundaries) with a safe fallback to `RecursiveCharacterTextSplitter`; token sizing uses **tiktoken** (fallback if unavailable). Default chunk budget aligns with **multilingual-e5** (~512 tokens). |
| **Classification** | `classification/rule_classifier.py`: keyword rules first; optional **Groq** per-chunk fallback when `CLASSIFY_USE_LLM=true` (default is off for speed). |
| **Embeddings** | `embedding/embedder.py`: **sentence-transformers** (default `intfloat/multilingual-e5-base`), `passage:` / `query:` prefixes for E5. |
| **Stores** | **ChromaDB** (`vectorstore/chroma_store.py`) + **BM25** (`retrieval/bm25_store.py` via `rank-bm25`), per-user on disk under `OUTPUT_DIR`. |
| **LLM** | **Groq** (`llm/`) for checklist JSON and Q&A; prompts stress grounding in retrieved context. |

---

## Statement-to-Implementation Traceability

| Problem statement claim | Implementation in this project | Status |
|---|---|---|
| Ingest multi-format governance documents (PDF, Word, spreadsheet, text, web, cloud links) | `ingestion/router.py` routes by extension/URL; loaders in `ingestion/pdf_loader.py`, `ingestion/word_loader.py`, `ingestion/excel_loader.py`, `ingestion/csv_loader.py`, `ingestion/scraper.py`, `ingestion/drive_loader.py` | Implemented |
| Use format-specific parsing including structure/table context where applicable | Word and web loaders preserve heading/table context (`content_type`, section metadata), PDF page-level extraction with OCR fallback | Implemented (best-effort by source quality) |
| Chunk content with contextual continuity and retrieval-ready metadata | `chunking/chunker.py` semantic chunking + overlap/fallback; per-chunk metadata (`chunk_id`, section heading, page, entities, table flag) | Implemented |
| Generate structured governance checklist items | `llm/generator.py` checklist generation + validation + normalization + dedupe/ranking | Implemented |
| Group checklist by compliance domains | `classification/rule_classifier.py` + checklist domain normalization in `llm/generator.py`; UI filters in `app.py` | Implemented |
| Ensure auditability/traceability back to source chunks | Retrieval context includes `chunk_id` + source metadata in `retrieval/retriever.py`; citation enforcement/abstention in `llm/generator.py` | Implemented |
| Export structured output to CSV/Excel/JSON | Streamlit exports in `app.py` (`CSV`, `Excel`, `JSON`, plus audit markdown report) | Implemented |
| Support scalable and reliable processing for larger jobs | Queue-based ingestion with Redis/Celery (`celery_app.py`, `ingestion/tasks.py`, `job_status.py`), worker recycling in compose/env | Implemented |

---

## Project layout

```
├── main.py              # FastAPI app, CORS, health endpoints, upload/chat APIs
├── app.py               # Streamlit UI
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── .env.example         # Copy to .env and set secrets
├── storage/db.py        # SQLite checklist history (SQLAlchemy)
├── ingestion/           # Loaders + router
├── chunking/            # chunker.py, token_utils.py
├── classification/      # rule_classifier.py, llm_classifier.py
├── embedding/           # embedder.py
├── vectorstore/         # chroma_store.py
├── retrieval/           # retriever.py, bm25_store.py
└── llm/                 # groq_client, generator, prompt_templates
```

---

## API (localhost:8000)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/upload` | `multipart/form-data`: `file` and/or `link`, `user_id`. Returns `job_id`. |
| GET | `/api/status/{job_id}` | `status`, `progress`, `message` (`completed` / `error`). |
| POST | `/api/chat` | JSON: `query`, `domain`, `user_id`. Retrieval + Groq; checklist-style queries return `raw_data` JSON. |
| POST | `/api/chat/stream` | Streaming text response for normal Q&A. |

Interactive docs: **http://127.0.0.1:8000/docs**

---

## Setup

### 1. Environment

Copy `.env.example` to `.env` and set at least:

```env
GROQ_API_KEY=your_key_here
GROQ_GENERATOR_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=intfloat/multilingual-e5-base
CHROMA_PERSIST_DIR=./chroma_db
OUTPUT_DIR=./output
```

Optional tuning (see code / comments in repo):

```env
API_URL=http://localhost:8000          # Streamlit → API
CLASSIFY_USE_LLM=false                  # true = Groq per chunk when rules miss (slower)
CLASSIFY_DEFAULT_DOMAIN=audit_compliance
CHUNK_MAX_TOKENS=512
CHUNK_OVERLAP=128
SEMANTIC_SIM_THRESHOLD=0.70
SEMANTIC_MIN_TOKENS=128
VERIFY_ENABLE=true
VERIFY_MIN_CONFIDENCE=0.80
RERANK_ENABLE=false
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANK_CANDIDATE_MULTIPLIER=2
RETRIEVAL_FETCH_MULTIPLIER=3
EMBEDDING_BATCH_SIZE=192
TORCH_NUM_THREADS=8                     # CPU only, optional
SAVE_CHUNK_JSONL=false                  # true = append chunks to output/chunked.jsonl
```

### 2. Install dependencies

```bash
python -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` includes **FastAPI**, **chromadb**, **sentence-transformers**, **streamlit**, **rank-bm25**, **groq**, and ingestion libraries. First embedding model load may download weights from Hugging Face.

### 3. Run (two terminals)

**Terminal 1 — API**

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — Streamlit (optional)**

```bash
streamlit run app.py --server.port 8501 --server.address 127.0.0.1
```

- **Streamlit:** http://127.0.0.1:8501  
- **API:** http://127.0.0.1:8000  

Keep the API running whenever you use Streamlit.

### 4. Docker

```bash
docker-compose up --build -d
```

Adjust ports and commands in `docker-compose.yml` / `Dockerfile` if you override defaults.

---

## Using the app

### Streamlit (`app.py`)

1. **Sidebar:** Upload a file or paste a URL, then **Process documents**. The app polls `/api/status/{job_id}` until completion, then calls `/api/chat` to build the checklist.
2. **Filter by domain:** Sidebar domain buttons narrow the checklist table.
3. **Start Over:** Clears session state (sidebar **Session** section and/or **Checklist** tab). Use this before a new document for a clean session.
4. **Checklist tab:** **CSV** export uses fixed columns (`requirement`, `domain`, `source_section`, `priority`, `action_type`, `evidence_required`, `chunk_id`, `source_url`, etc.). **JSON** / **Excel** export full row payloads.
5. **RAG Chat tab:** Questions go to `/api/chat/stream` (or `/api/chat` for checklist-style phrasing).

---

## Troubleshooting

| Issue | What to check |
|--------|----------------|
| `No module named 'rank_bm25'` | `pip install rank-bm25` (listed in `requirements.txt`). |
| Ingestion errors | `GROQ_API_KEY`, disk space, `CHROMA_PERSIST_DIR` / `OUTPUT_DIR` writable. |
| Empty checklist | Model/key errors; ensure upload completed (`status` = `completed`) and `user_id` matches between upload and chat. |
| Port already in use | Change `--port` for uvicorn or Streamlit, or stop the old process. |

---

## License / compliance

Use in line with your organization’s policies and the terms of Groq, Hugging Face models, and third-party document sources.
