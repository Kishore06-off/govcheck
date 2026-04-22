import hashlib
import json
import os
import time
from typing import Optional


def _manifest_path(user_id: str) -> str:
    output_dir = os.getenv("OUTPUT_DIR", "./output")
    user_dir = os.path.join(output_dir, user_id)
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, "ingestion_manifest.json")


def _load_manifest(user_id: str) -> dict:
    p = _manifest_path(user_id)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_manifest(user_id: str, data: dict) -> None:
    p = _manifest_path(user_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_source_fingerprint(file_path: str, filename: str = "") -> str:
    """
    Build a stable fingerprint for ingestion dedupe.
    - URL input: hash URL string
    - Local file: hash bytes + filename
    """
    h = hashlib.sha256()
    if file_path.startswith("http://") or file_path.startswith("https://"):
        h.update(file_path.encode("utf-8"))
        if filename:
            h.update(filename.encode("utf-8"))
        return h.hexdigest()

    h.update((filename or os.path.basename(file_path)).encode("utf-8"))
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def lookup_fingerprint(user_id: str, fingerprint: str) -> Optional[dict]:
    manifest = _load_manifest(user_id)
    rec = manifest.get(fingerprint)
    if not isinstance(rec, dict):
        return None
    # Never reuse known-empty ingestions.
    try:
        if int(rec.get("chunks", 0) or 0) <= 0:
            return None
    except Exception:
        return None
    return rec


def record_fingerprint(user_id: str, fingerprint: str, chunks: int, source_name: str) -> None:
    manifest = _load_manifest(user_id)
    manifest[fingerprint] = {
        "chunks": int(chunks),
        "source_name": source_name,
        "updated_at": int(time.time()),
    }
    _save_manifest(user_id, manifest)

