from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
import os
import uuid
import logging
import time
import re
import ipaddress
from urllib.parse import urlparse
from typing import Optional
from job_status import get_status as get_job_status, set_status
from api.security import require_api_key, enforce_rate_limit

# Setup directories
os.makedirs("./output", exist_ok=True)

app = FastAPI(title="Governance AI API", version="2.0")
logger = logging.getLogger("govcheck.api")
if not logger.handlers:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

# CORS for frontend decoupling
cors_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",") if o.strip()]
allow_all_origins = os.getenv("CORS_ALLOW_ALL", "false").lower() in ("1", "true", "yes")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

import threading

def _prewarm_model():
    try:
        print("Pre-warming embedding model (background thread)...")
        from embedding.embedder import get_model
        get_model()
        print("Embedding model ready.")
    except Exception as e:
        print(f"Warning: Model pre-warm failed: {e}")

# Startup: Init db immediately; warm model in background so server starts fast
@app.on_event("startup")
async def startup_event():
    print("Initializing Database...")
    from storage.db import init_db
    init_db()
    # Warm model in background thread — server accepts requests immediately
    t = threading.Thread(target=_prewarm_model, daemon=True)
    t.start()
    print("Server ready. Model warming up in background...")

# Status dictionary to track ingestion progress
QUEUE_ENABLED = os.getenv("QUEUE_ENABLED", "true").lower() in ("1", "true", "yes")

class ChatTurn(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str):
        if v not in {"user", "assistant", "system"}:
            raise ValueError("role must be one of: user, assistant, system")
        return v


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    domain: Optional[str] = "all"
    user_id: Optional[str] = "anonymous"
    history: Optional[list[ChatTurn]] = None

_SAFE_USER_ID_RE = re.compile(r"[^a-zA-Z0-9_\-]")
_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

def _safe_user_id(user_id: str) -> str:
    cleaned = _SAFE_USER_ID_RE.sub("_", (user_id or "anonymous").strip())
    return cleaned[:64] if cleaned else "anonymous"

def _validate_link_input(link: str) -> None:
    parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid link. Only http/https URLs are allowed.")
    allow_private = os.getenv("ALLOW_PRIVATE_LINKS", "false").lower() in ("1", "true", "yes")
    host = parsed.hostname or ""
    if not allow_private:
        lowered = host.lower()
        if lowered in ("localhost",):
            raise HTTPException(status_code=400, detail="Private/local URLs are not allowed.")
        try:
            ip = ipaddress.ip_address(lowered)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise HTTPException(status_code=400, detail="Private/local URLs are not allowed.")
        except ValueError:
            # Not an IP literal; keep as hostname.
            pass

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error request_id=%s path=%s method=%s", request_id, request.url.path, request.method)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response

def _enqueue_ingestion(file_path: str, filename: str, job_id: str, user_id: str) -> None:
    """
    Prefer Celery worker execution. Fallback to in-process BackgroundTasks for local/dev.
    """
    if QUEUE_ENABLED:
        try:
            from ingestion.tasks import run_ingestion_pipeline as celery_task

            celery_task.delay(file_path, filename, job_id, user_id)
            return
        except Exception:
            # Fall back to BackgroundTasks path if Celery isn't configured.
            pass

    # Fallback (legacy) execution
    from ingestion.tasks import run_ingestion_pipeline as legacy_task
    legacy_task(file_path, filename, job_id, user_id)

@app.post("/api/upload")
async def upload_file(request: Request, background_tasks: BackgroundTasks, file: Optional[UploadFile] = File(None), link: Optional[str] = Form(None), user_id: str = Form("anonymous")):
    require_api_key(request)
    enforce_rate_limit(f"upload:{_safe_user_id(user_id)}")
    job_id = str(uuid.uuid4())
    user_id = _safe_user_id(user_id)
    os.makedirs(f"output/{user_id}", exist_ok=True)
    max_upload_mb = max(1, int(os.getenv("MAX_UPLOAD_MB", "100")))
    
    if link:
        # Process as a cloud link / webpage
        _validate_link_input(link)
        file_path = link
        filename = link
    elif file:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext and ext not in _ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        # Process as a physical file upload
        file_path = os.path.join(f"output/{user_id}", f"{job_id}_{file.filename}")  
        max_bytes = max_upload_mb * 1024 * 1024
        total = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    f.close()
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                    raise HTTPException(status_code=413, detail=f"File too large. Max upload size is {max_upload_mb}MB.")
                f.write(chunk)
        filename = file.filename
    else:
        raise HTTPException(status_code=400, detail="Must provide either a file or a link")

    set_status(job_id, {"status": "queued", "progress": 0, "message": "Job queued"})

    # Prefer queue mode via Celery; enqueue quickly so API stays responsive
    background_tasks.add_task(_enqueue_ingestion, file_path, filename, job_id, user_id)
    return {"job_id": job_id, "message": "Upload successful, processing in background"}

@app.get("/api/status/{job_id}")
async def get_status(request: Request, job_id: str):
    require_api_key(request)
    enforce_rate_limit(f"status:{job_id}")
    status = get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status

@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest, request: Request):
    require_api_key(request)
    enforce_rate_limit(f"chat:{_safe_user_id(payload.user_id or 'anonymous')}")
    from retrieval.retriever import retrieve_and_format
    from llm.generator import generate_answer, generate_checklist

    query_lower = payload.query.lower()
    is_checklist = "checklist" in query_lower or "map " in query_lower
    
    # EFFICIENCY FIX: Non-blocking threadpool offloaded execution
    # Fetch top 50 chunks for full checklist generation instead of 5
    fetch_amount = 50 if is_checklist else 5
    results, context_string = await run_in_threadpool(
        retrieve_and_format, payload.query, payload.domain, top_k=fetch_amount, user_id=payload.user_id
    )

    if not results or not context_string:
        return {"response": "No relevant context found in documents. Please ensure valid governance documents are uploaded and indexed."}

    if is_checklist:
        checklist_items = await run_in_threadpool(generate_checklist, context_string, results)
        if not checklist_items:
            return {"response": "Failed to generate structured checklist from the context.", "raw_data": None}

        # Format the JSON items into a beautiful markdown string for Streamlit UI
        from storage.db import save_checklist
        save_checklist(payload.query, checklist_items, payload.user_id)

        md_lines = ["### Compliance Extraction Request\n"]
        for it in checklist_items:
            md_lines.append(f"- **Domain:** {it.get('domain', 'general').capitalize()}\n  **Requirement:** {it.get('item', '')}")
            if it.get("source_section") and it.get("source_section") not in ["—", "â€”"]:  
                md_lines.append(f"  *(Source Section: {it['source_section']})*")

        answer_string = "\n".join(md_lines)
        return {"response": answer_string, "raw_data": checklist_items}
    else:
        # Otherwise, use standard Chat Q&A
        # Pass only last 8 turns into the answer prompt (if provided)
        history = payload.history or []
        history = history[-8:]
        if history:
            history_blob = "\n".join([f"{t.role.upper()}: {t.content}" for t in history])
            q = f"{payload.query}\n\nConversation (last {len(history)} turns):\n{history_blob}"
        else:
            q = payload.query

        answer_string = await run_in_threadpool(generate_answer, q, context_string)
        return {"response": answer_string, "raw_data": None}

@app.post("/api/chat/stream")
async def chat_endpoint_stream(payload: ChatRequest, request: Request):
    require_api_key(request)
    enforce_rate_limit(f"chat_stream:{_safe_user_id(payload.user_id or 'anonymous')}")
    from retrieval.retriever import retrieve_and_format
    from llm.generator import stream_answer
    from fastapi.responses import StreamingResponse

    # EFFICIENCY FIX: Non-blocking threadpool offloaded execution
    results, context_string = await run_in_threadpool(
        retrieve_and_format, payload.query, payload.domain, top_k=5, user_id=payload.user_id
    )

    if not results or not context_string:
        async def mock_stream():
            yield "No relevant context found in documents. Please ensure valid governance documents are uploaded and indexed."
        return StreamingResponse(mock_stream(), media_type="text/plain")

    # Use standard Chat Q&A via stream (include last 8 turns if provided)
    history = payload.history or []
    history = history[-8:]
    if history:
        history_blob = "\n".join([f"{t.role.upper()}: {t.content}" for t in history])
        q = f"{payload.query}\n\nConversation (last {len(history)} turns):\n{history_blob}"
    else:
        q = payload.query

    generator = stream_answer(q, context_string)
    
    async def generate():
        for chunk in generator:
            yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/")
async def root():
    return {"status": "ok", "service": "govcheck-api", "queue_enabled": QUEUE_ENABLED}

@app.get("/health/live")
async def health_live():
    return {"status": "ok"}

@app.get("/health/ready")
async def health_ready():
    checks = {"db": False, "redis": False}
    # DB check
    try:
        from storage.db import SessionLocal
        from sqlalchemy import text
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        checks["db"] = False
    # Redis check (optional in local mode, required when queue enabled)
    try:
        import redis
        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False
    ready = checks["db"] and (checks["redis"] or not QUEUE_ENABLED)
    status = 200 if ready else 503
    return JSONResponse(status_code=status, content={"ready": ready, "checks": checks, "queue_enabled": QUEUE_ENABLED})

