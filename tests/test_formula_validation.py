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
from app.services.formula_engine import FormulaEngine
from app.models.entities import FormulaTemplate


@pytest.fixture
def client_with_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Pre-seed
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
    login_resp = client.post("/api/auth/login", json={"user_id": 1})
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    yield client, TestingSession, headers
    app.dependency_overrides.clear()


def test_put_formula_with_typo_returns_400(client_with_db):
    client, _, headers = client_with_db
    resp = client.put(
        "/api/formulas/templates/1",
        json={"formula_expression": "IF(deals_won_sum_typo >= plan_sales, base_rate * 0.7, base_rate * 0.1)"},
        headers=headers
    )
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "deals_won_sum_typo" in detail
    assert "Неизвестные переменные" in detail


def test_put_formula_with_valid_expression_returns_200(client_with_db):
    client, _, headers = client_with_db
    resp = client.put(
        "/api/formulas/templates/1",
        json={"formula_expression": "IF(deals_won_sum >= plan_sales, base_rate * 0.75, base_rate * 0.2)"},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["formula_expression"] == "IF(deals_won_sum >= plan_sales, base_rate * 0.75, base_rate * 0.2)"


def test_sandbox_test_with_typo_reports_unknown_vars(client_with_db):
    client, _, headers = client_with_db
    resp = client.post(
        "/api/formulas/sandbox/test",
        json={"expression": "deals_won_sum_typo + 10"},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["unknown_vars"] == ["deals_won_sum_typo"]
    assert "deals_won_sum_typo" in data["error"]


def test_formulas_endpoints_require_authentication(client_with_db):
    client, _, _ = client_with_db
    # Unauthenticated /sandbox/test returns 401
    resp1 = client.post("/api/formulas/sandbox/test", json={"expression": "10 + 20"})
    assert resp1.status_code == 401

    # Unauthenticated /templates returns 401
    resp2 = client.get("/api/formulas/templates")
    assert resp2.status_code == 401


def test_all_seed_formulas_pass_validation(client_with_db):
    _, session_factory, _ = client_with_db
    db = session_factory()
    try:
        templates = db.query(FormulaTemplate).all()
        assert len(templates) > 0
        for tpl in templates:
            # validate() should not raise FormulaError
            FormulaEngine.validate(tpl.formula_expression)
    finally:
        db.close()
