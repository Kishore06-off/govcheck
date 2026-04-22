import os

from fastapi.testclient import TestClient


os.environ.setdefault("API_AUTH_REQUIRED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("QUEUE_ENABLED", "false")

from main import app  # noqa: E402


client = TestClient(app)


def test_health_live():
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_root():
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") == "ok"
    assert body.get("service") == "govcheck-api"


def test_upload_requires_file_or_link():
    res = client.post("/api/upload", data={"user_id": "test"})
    assert res.status_code == 400
    assert "Must provide either a file or a link" in res.text


def test_chat_validation_empty_query():
    payload = {"query": "", "domain": "all", "user_id": "test"}
    res = client.post("/api/chat", json=payload)
    assert res.status_code in (400, 422)

