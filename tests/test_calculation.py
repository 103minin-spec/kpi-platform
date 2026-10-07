import pytest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import Base
from app.seed import seed_database
from app.services.calculation_service import CalculationService
from app.models.entities import Period, CalculationResult


@pytest.fixture
def test_db():
    # Use isolated in-memory database for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()
    seed_database(db)
    yield db
    db.close()


@pytest.mark.anyio
async def test_calculation_and_lock_pipeline(test_db):
    db = test_db
    period = db.query(Period).first()
    assert period is not None
    assert period.status == "DRAFT"

    # Run calculation
    res = await CalculationService.calculate_period(period.id, db)
    assert res["status"] == "CALCULATED"
    assert res["employees_calculated"] > 0

    # Verify calculation results exist
    calc_results = db.query(CalculationResult).filter(CalculationResult.period_id == period.id).all()
    assert len(calc_results) == res["employees_calculated"]

    for r in calc_results:
        assert r.total_payout >= 0
        assert r.kpi_percent >= 0
        assert r.raw_metrics is not None

    # Test lock
    locked_period = CalculationService.lock_period(period.id, db)
    assert locked_period.status == "LOCKED"
    assert locked_period.locked_at is not None

    # Verify recalculating locked period raises ValueError
    with pytest.raises(ValueError, match="заблокирован"):
        await CalculationService.calculate_period(period.id, db)


@pytest.mark.anyio
async def test_kpi_percent_is_zero_without_facts(test_db, monkeypatch):
    db = test_db
    period = db.query(Period).first()
    assert period is not None

    async def mock_zero_metrics(*args, **kwargs):
        return {
            "deals_won_sum": 0.0,
            "deals_won_count": 0.0,
            "deals_total_count": 0.0,
            "conversion_rate": 0.0,
            "tasks_closed": 0.0,
            "tasks_overdue": 0.0,
            "tasks_total": 0.0,
            "tasks_on_time_pct": 0.0,
            "calls_count": 0.0,
            "calls_duration_minutes": 0.0,
        }

    from app.services.bitrix_service import bitrix_service
    monkeypatch.setattr(bitrix_service, "get_employee_metrics", mock_zero_metrics)

    res = await CalculationService.calculate_period(period.id, db)
    assert res["status"] == "CALCULATED"

    calc_results = db.query(CalculationResult).filter(CalculationResult.period_id == period.id).all()
    assert len(calc_results) > 0

    sales_checked = 0
    for r in calc_results:
        assert r.kpi_percent != 100.0
        plan_sales = r.computed_variables.get("plan_sales", 0.0)
        if plan_sales > 0:
            assert r.kpi_percent == 0.0
            sales_checked += 1

    assert sales_checked > 0


@pytest.mark.anyio
async def test_calculation_warnings_when_no_individual_targets(test_db):
    db = test_db
    # Create a fresh period with no EmployeeTargets
    new_period = Period(
        name="Ноябрь 2026 (без планов)",
        start_date="2026-11-01",
        end_date="2026-11-30",
        status="DRAFT"
    )
    db.add(new_period)
    db.commit()
    db.refresh(new_period)

    res = await CalculationService.calculate_period(new_period.id, db)
    assert res["status"] == "CALCULATED"
    assert "warnings" in res
    assert len(res["warnings"]) > 0
    assert any("нет индивидуального плана" in w for w in res["warnings"])


@pytest.mark.anyio
async def test_calculation_formula_error_sets_status_error(test_db):
    db = test_db
    from app.models.entities import FormulaTemplate
    
    # Set one formula template to an expression that triggers division by zero
    tpl = db.query(FormulaTemplate).first()
    tpl.formula_expression = "1 / 0"
    db.commit()

    period = db.query(Period).first()
    res = await CalculationService.calculate_period(period.id, db)
    assert res["status"] == "CALCULATED"

    error_result = db.query(CalculationResult).filter(
        CalculationResult.period_id == period.id,
        CalculationResult.formula_template_id == tpl.id
    ).first()
    assert error_result is not None
    assert error_result.status == "ERROR"
    assert error_result.bonus_amount == 0.0
    assert "Ошибка формулы" in error_result.notes

