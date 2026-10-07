import pytest
import sys
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, get_db
from app.main import app
from app.seed import seed_database
from app.services.bitrix_service import bitrix_service


@pytest.fixture
def settings_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    init_db = TestingSession()
    seed_database(init_db)
    init_db.close()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # Login as admin
    resp = client.post("/api/auth/login", json={"user_id": 1})
    assert resp.status_code == 200
    token = resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {token}"}

    yield client, admin_headers, TestingSession
    app.dependency_overrides.clear()


def test_put_invalid_webhook_url_returns_422(settings_client):
    client, admin_headers, _ = settings_client
    # Not https
    resp = client.put(
        "/api/settings/bitrix",
        json={"webhook_url": "http://myportal.bitrix24.ru/rest/1/abc/"},
        headers=admin_headers
    )
    assert resp.status_code == 422

    # Missing /rest/
    resp2 = client.put(
        "/api/settings/bitrix",
        json={"webhook_url": "https://myportal.bitrix24.ru/api/1/abc/"},
        headers=admin_headers
    )
    assert resp2.status_code == 422


def test_put_valid_webhook_url_saves_and_returns_masked(settings_client):
    client, admin_headers, session_factory = settings_client
    valid_url = "https://myportal.bitrix24.ru/rest/1/secrettoken123/"
    resp = client.put(
        "/api/settings/bitrix",
        json={"webhook_url": valid_url},
        headers=admin_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["webhook_url_masked"] == "https://myportal.bitrix24.ru/rest/1/****"
    assert "secrettoken123" not in data["webhook_url_masked"]

    # Verify GET returns masked URL
    get_resp = client.get("/api/settings/bitrix", headers=admin_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["webhook_url_masked"] == "https://myportal.bitrix24.ru/rest/1/****"


def test_test_connection_in_mock_mode_returns_ok_true(settings_client):
    client, admin_headers, _ = settings_client
    bitrix_service.mock_mode = True
    resp = client.post("/api/settings/bitrix/test", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["mode"] == "mock"


@pytest.mark.anyio
async def test_test_connection_live_mode_error(settings_client, monkeypatch):
    client, admin_headers, _ = settings_client
    bitrix_service.mock_mode = False
    bitrix_service.webhook_url = "https://nonexistent.bitrix24.ru/rest/1/abc/"

    # Mock httpx failure
    import httpx

    async def mock_get(*args, **kwargs):
        raise httpx.ConnectError("Connection refused to portal")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    resp = client.post("/api/settings/bitrix/test", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "Connection refused" in data["error"]
    bitrix_service.mock_mode = True  # Reset to mock mode


def test_put_masked_url_returns_422(settings_client):
    client, admin_headers, _ = settings_client
    resp = client.put(
        "/api/settings/bitrix",
        json={"webhook_url": "https://portal.bitrix24.ru/rest/1/****"},
        headers=admin_headers
    )
    assert resp.status_code == 422


def test_put_empty_string_does_not_erase_saved_webhook(settings_client):
    client, admin_headers, _ = settings_client
    # 1. Save valid webhook
    resp = client.put(
        "/api/settings/bitrix",
        json={"webhook_url": "https://portal.bitrix24.ru/rest/1/mysecretkey/"},
        headers=admin_headers
    )
    assert resp.status_code == 200
    assert "portal.bitrix24.ru" in resp.json()["webhook_url_masked"]

    # 2. PUT empty string: must NOT erase saved webhook
    resp_empty = client.put(
        "/api/settings/bitrix",
        json={"webhook_url": ""},
        headers=admin_headers
    )
    assert resp_empty.status_code == 200
    assert "portal.bitrix24.ru" in resp_empty.json()["webhook_url_masked"]
    assert bitrix_service.webhook_url == "https://portal.bitrix24.ru/rest/1/mysecretkey/"


def test_put_clear_webhook_clears_saved_url(settings_client):
    client, admin_headers, _ = settings_client
    # Save valid webhook
    client.put(
        "/api/settings/bitrix",
        json={"webhook_url": "https://portal.bitrix24.ru/rest/1/mysecretkey/"},
        headers=admin_headers
    )
    # Clear webhook
    resp_clear = client.put(
        "/api/settings/bitrix",
        json={"clear_webhook": True},
        headers=admin_headers
    )
    assert resp_clear.status_code == 200
    assert not resp_clear.json()["webhook_url_masked"]
    assert bitrix_service.webhook_url == ""

