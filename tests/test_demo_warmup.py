import pytest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base
from app.models.entities import CalculationResult, Period
from app.seed import seed_database
from app.services.bitrix_service import bitrix_service
from app.services.calculation_service import CalculationService
from app.services.demo_service import warmup_demo_data


@pytest.fixture
def demo_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    seed_database(session)
    yield session
    session.close()


@pytest.mark.anyio
async def test_warmup_calculates_latest_period_once(demo_db):
    bitrix_service.mock_mode = True
    latest = demo_db.query(Period).order_by(Period.id.desc()).first()
    assert demo_db.query(CalculationResult).filter_by(period_id=latest.id).count() == 0

    result = await warmup_demo_data(demo_db)
    assert result is not None
    assert result["employees_calculated"] > 0
    assert demo_db.query(CalculationResult).filter_by(period_id=latest.id).count() > 0

    # Повторный запуск ничего не пересчитывает
    assert await warmup_demo_data(demo_db) is None


@pytest.mark.anyio
async def test_warmup_skipped_in_live_mode(demo_db):
    bitrix_service.mock_mode = False
    try:
        assert await warmup_demo_data(demo_db) is None
    finally:
        bitrix_service.mock_mode = True


@pytest.mark.anyio
async def test_seed_fills_targets_for_every_period(demo_db):
    """Демо-данные должны содержать индивидуальные планы на каждый период: расчет без предупреждений."""
    bitrix_service.mock_mode = True
    periods = demo_db.query(Period).order_by(Period.id).all()
    assert len(periods) >= 2
    for period in periods:
        result = await CalculationService.calculate_period(period.id, demo_db)
        assert result["warnings"] == [], f"Период {period.name}: {result['warnings']}"
