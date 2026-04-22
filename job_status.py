import json
import os
import time
from typing import Any, Optional

_MEM_STATUS: dict[str, dict[str, Any]] = {}


def _redis_client():
    """
    Lazily create a Redis client.
    If Redis is unavailable or the dependency isn't installed, return None.
    """
    try:
        import redis  # type: ignore
    except Exception:
        return None

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _key(job_id: str) -> str:
    prefix = os.getenv("JOB_STATUS_KEY_PREFIX", "govcheck:job")
    return f"{prefix}:{job_id}"


def set_status(job_id: str, payload: dict[str, Any]) -> None:
    ttl = int(os.getenv("JOB_STATUS_TTL_SEC", "3600"))
    payload = dict(payload)
    payload.setdefault("updated_at", int(time.time()))

    # Always store in-process as a fallback (useful for local/dev without Redis).
    _MEM_STATUS[job_id] = payload

    r = _redis_client()
    if r is None:
        return
    r.setex(_key(job_id), ttl, json.dumps(payload, ensure_ascii=False))


def get_status(job_id: str) -> Optional[dict[str, Any]]:
    r = _redis_client()
    if r is None:
        return _MEM_STATUS.get(job_id)
    raw = r.get(_key(job_id))
    if not raw:
        return _MEM_STATUS.get(job_id)
    try:
        return json.loads(raw)
    except Exception:
        return _MEM_STATUS.get(job_id)

