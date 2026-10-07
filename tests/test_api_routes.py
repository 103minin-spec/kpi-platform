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
def routes_client():
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

    def login_user(user_id: int):
        resp = client.post("/api/auth/login", json={"user_id": user_id})
        assert resp.status_code == 200
        token = resp.json()["token"]
        return {"Authorization": f"Bearer {token}"}

    yield client, login_user
    app.dependency_overrides.clear()


def test_bitrix_toggle_mock_route_exists_in_openapi():
    paths = app.openapi()["paths"]
    assert "/api/auth/bitrix/toggle-mock" in paths
    assert "post" in paths["/api/auth/bitrix/toggle-mock"]


def test_toggle_mock_mode_admin_succeeds_and_employee_forbidden(routes_client):
    client, login_user = routes_client
    admin_headers = login_user(user_id=1)
    emp_headers = login_user(user_id=3)

    # 1. Employee cannot toggle mock
    resp_emp = client.post("/api/auth/bitrix/toggle-mock?enabled=false", headers=emp_headers)
    assert resp_emp.status_code == 403

    # 2. Admin can toggle mock
    resp_admin = client.post("/api/auth/bitrix/toggle-mock?enabled=false", headers=admin_headers)
    assert resp_admin.status_code == 200
    assert resp_admin.json()["mock_mode"] is False
    assert bitrix_service.mock_mode is False

    # Toggle back to True
    resp_admin_true = client.post("/api/auth/bitrix/toggle-mock?enabled=true", headers=admin_headers)
    assert resp_admin_true.status_code == 200
    assert resp_admin_true.json()["mock_mode"] is True
    assert bitrix_service.mock_mode is True


def test_toggle_mock_mode_persists_in_db(routes_client):
    client, login_user = routes_client
    admin_headers = login_user(user_id=1)

    # Toggle to False
    resp = client.post("/api/auth/bitrix/toggle-mock?enabled=false", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["mock_mode"] is False

    from app.services.settings_service import SettingsService
    db = next(app.dependency_overrides[get_db]())
    val = SettingsService.get_setting(db, "bitrix_mock_mode")
    assert val == "false"

    # Re-init settings from DB: mock_mode should remain False
    SettingsService.init_settings(db)
    assert bitrix_service.mock_mode is False

    # Toggle back to True
    client.post("/api/auth/bitrix/toggle-mock?enabled=true", headers=admin_headers)
    assert SettingsService.get_setting(db, "bitrix_mock_mode") == "true"
    db.close()

