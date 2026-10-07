import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.seed import seed_database
from app.models.entities import User, UserSession


@pytest.fixture
def validation_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    init_db = TestingSession()
    seed_database(init_db)
    
    admin_user = init_db.query(User).filter(User.role == "ADMIN").first()
    admin_session = UserSession(token="admin-token-val-test", user_id=admin_user.id)
    init_db.add(admin_session)
    init_db.commit()
    init_db.close()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client, "admin-token-val-test"
    app.dependency_overrides.clear()


def test_period_create_invalid_date_format_returns_422(validation_client):
    client, token = validation_client
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": "Тестовый период",
        "start_date": "01.12.2026",
        "end_date": "31.12.2026"
    }
    resp = client.post("/api/periods", json=payload, headers=headers)
    assert resp.status_code == 422


def test_period_create_start_date_greater_than_end_date_returns_422(validation_client):
    client, token = validation_client
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": "Период с ошибкой дат",
        "start_date": "2026-11-01",
        "end_date": "2026-10-01"
    }
    resp = client.post("/api/periods", json=payload, headers=headers)
    assert resp.status_code == 422


def test_target_update_negative_base_rate_returns_422(validation_client):
    client, token = validation_client
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "base_rate": -50000.0,
        "plan_sales": 300000.0,
        "plan_tasks": 20.0,
        "target_calls": 100.0,
        "quality_score": 100.0
    }
    resp = client.put("/api/company/periods/1/targets/1", json=payload, headers=headers)
    assert resp.status_code == 422


def test_target_update_invalid_quality_score_returns_422(validation_client):
    client, token = validation_client
    headers = {"Authorization": f"Bearer {token}"}
    
    # quality_score > 100
    resp1 = client.put("/api/company/periods/1/targets/1", json={"quality_score": 150.0}, headers=headers)
    assert resp1.status_code == 422

    # quality_score < 1
    resp2 = client.put("/api/company/periods/1/targets/1", json={"quality_score": 0.0}, headers=headers)
    assert resp2.status_code == 422
