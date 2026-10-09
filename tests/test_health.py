"""
Tests for the /health endpoint.

Uses FastAPI's TestClient (backed by httpx) so we don't need
a running server — requests go directly to the ASGI app in-process.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    """GET /health should return 200 with {"status": "ok"}."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_docs() -> None:
    """GET / should redirect to /docs with HTTP 307."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
