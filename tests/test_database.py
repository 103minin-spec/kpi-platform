import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db, engine as app_engine
from app.models.entities import Department, Position, User, UserSession
from app.main import app
from app.seed import seed_database


def test_sqlite_foreign_keys_pragma_enabled():
    with app_engine.connect() as conn:
        res = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert res == 1


def test_sqlite_foreign_keys_cascade_delete():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    # Create department and position
    dept = Department(name="Test Dept Cascade", description="Cascade test")
    db.add(dept)
    db.commit()
    db.refresh(dept)

    pos = Position(department_id=dept.id, name="Test Pos Cascade")
    db.add(pos)
    db.commit()
    db.refresh(pos)

    pos_id = pos.id
    dept_id = dept.id

    # Verify both exist
    assert db.query(Position).filter(Position.id == pos_id).first() is not None

    # Delete department directly via SQL to verify SQLite engine-level cascade
    db.execute(text("DELETE FROM departments WHERE id = :did"), {"did": dept_id})
    db.commit()

    # Position must have been cascade deleted by SQLite foreign key constraint
    remaining_pos = db.query(Position).filter(Position.id == pos_id).first()
    assert remaining_pos is None, "Position should have been cascade deleted when department was deleted"
    db.close()


@pytest.fixture
def db_test_env():
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
    admin_session = UserSession(token="admin-token-db-test", user_id=admin_user.id)
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
    yield client, "admin-token-db-test"
    app.dependency_overrides.clear()


def test_put_targets_nonexistent_period_returns_404(db_test_env):
    client, token = db_test_env
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "base_rate": 60000,
        "plan_sales": 400000,
        "plan_tasks": 20,
        "target_calls": 100,
        "quality_score": 100
    }
    resp = client.put("/api/company/periods/999999/targets/1", json=payload, headers=headers)
    assert resp.status_code == 404
    assert "Период не найден" in resp.json()["detail"]


def test_put_targets_nonexistent_user_returns_404(db_test_env):
    client, token = db_test_env
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "base_rate": 60000,
        "plan_sales": 400000,
        "plan_tasks": 20,
        "target_calls": 100,
        "quality_score": 100
    }
    resp = client.put("/api/company/periods/1/targets/999999", json=payload, headers=headers)
    assert resp.status_code == 404
    assert "Сотрудник не найден" in resp.json()["detail"]


def test_calculate_nonexistent_period_returns_404(db_test_env):
    client, token = db_test_env
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/periods/999999/calculate", headers=headers)
    assert resp.status_code == 404
    assert "Период не найден" in resp.json()["detail"]


def test_lock_nonexistent_period_returns_404(db_test_env):
    client, token = db_test_env
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/periods/999999/lock", headers=headers)
    assert resp.status_code == 404
    assert "Период не найден" in resp.json()["detail"]
