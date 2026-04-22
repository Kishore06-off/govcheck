import os
import time
import threading
from collections import deque
from typing import Optional

from fastapi import HTTPException, Request


_lock = threading.Lock()
_bucket: dict[str, deque[float]] = {}


def _is_auth_required() -> bool:
    return os.getenv("API_AUTH_REQUIRED", "false").lower() in ("1", "true", "yes")


def _api_key() -> str:
    return os.getenv("API_KEY", "").strip()


def require_api_key(request: Request) -> None:
    """
    Optional API key auth.
    Enabled only when API_AUTH_REQUIRED=true.
    """
    if not _is_auth_required():
        return
    expected = _api_key()
    if not expected:
        raise HTTPException(status_code=500, detail="API auth is required but API_KEY is not configured.")
    x_api_key: Optional[str] = request.headers.get("X-API-Key")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def enforce_rate_limit(identity: str) -> None:
    """
    Lightweight in-process sliding-window rate limiter.
    Best effort for single-instance deployments.
    """
    enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("1", "true", "yes")
    if not enabled:
        return
    max_requests = max(1, int(os.getenv("RATE_LIMIT_REQUESTS", "60")))
    per_seconds = max(1, int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60")))
    now = time.time()

    with _lock:
        q = _bucket.setdefault(identity, deque())
        cutoff = now - per_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= max_requests:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        q.append(now)

