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
from app.services.calculation_service import CalculationService
from app.models.entities import Period


@pytest.fixture
def auth_test_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    init_db = TestingSession()
    seed_database(init_db)
    
    # Calculate period 1 so results exist
    period = init_db.query(Period).first()
    import anyio
    anyio.run(CalculationService.calculate_period, period.id, init_db)
    init_db.close()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # Helper to get auth header
    def login_user(user_id: int):
        resp = client.post("/api/auth/login", json={"user_id": user_id})
        assert resp.status_code == 200
        token = resp.json()["token"]
        return {"Authorization": f"Bearer {token}"}

    yield client, login_user
    app.dependency_overrides.clear()


def test_unauthorized_request_returns_401(auth_test_env):
    client, _ = auth_test_env
    resp = client.get("/api/periods/1/results")
    assert resp.status_code == 401


def test_employee_sees_only_own_results(auth_test_env):
    client, login_user = auth_test_env
    emp_headers = login_user(user_id=3)  # Дмитрий Соколов (EMPLOYEE)
    resp = client.get("/api/periods/1/results", headers=emp_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == 3


def test_head_sees_only_department_results(auth_test_env):
    client, login_user = auth_test_env
    head_headers = login_user(user_id=2)  # Михаил Воронов (HEAD, Sales dept 1)
    resp = client.get("/api/periods/1/results", headers=head_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Department 1 has users 2, 3, 4
    user_ids = {r["user_id"] for r in data}
    assert user_ids == {2, 3, 4}
    assert len(data) == 3


def test_employee_cannot_elevate_role_via_query_params(auth_test_env):
    client, login_user = auth_test_env
    emp_headers = login_user(user_id=3)
    resp = client.get("/api/periods/1/results?role=ADMIN&user_id=1", headers=emp_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == 3


def test_employee_cannot_modify_formulas(auth_test_env):
    client, login_user = auth_test_env
    emp_headers = login_user(user_id=3)
    resp = client.put(
        "/api/formulas/templates/1",
        json={"formula_expression": "base_rate * 2"},
        headers=emp_headers
    )
    assert resp.status_code == 403
