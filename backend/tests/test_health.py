from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.main import app, get_database


def test_health_reports_connected_database_and_no_analysis_run():
    database = AsyncMock()
    database.command.return_value = {"ok": 1}
    app.dependency_overrides[get_database] = lambda: database
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"service": "ok", "mongodb": "ok", "active_run": None}
    finally:
        app.dependency_overrides.clear()


def test_database_failure_returns_503_without_leaking_connection_details():
    database = AsyncMock()
    database.command.side_effect = ServerSelectionTimeoutError("private-connection-detail")
    app.dependency_overrides[get_database] = lambda: database
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        assert response.status_code == 503
        assert response.json() == {"service": "degraded", "mongodb": "unavailable", "active_run": None}
        assert "private-connection-detail" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_liveness_does_not_require_database():
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "alive"}
        assert client.get("/api/v1/portfolios").status_code == 404
