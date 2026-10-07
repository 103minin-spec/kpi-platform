"""
API router for Billing Periods, Periodic Calculation, and Snapshot Results.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Period, CalculationResult, User
from app.schemas.schemas import PeriodCreate
from app.services.calculation_service import CalculationService
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/api/periods", tags=["Periods"])


@router.get("")
def list_periods(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists all periods with their status and calculation summary."""
    periods = db.query(Period).order_by(Period.id.desc()).all()
    out = []
    for p in periods:
        res_count = db.query(CalculationResult).filter(CalculationResult.period_id == p.id).count()
        out.append({
            "id": p.id,
            "name": p.name,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "locked_at": p.locked_at.isoformat() if p.locked_at else None,
            "results_count": res_count
        })
    return out


@router.post("")
def create_period(
    payload: PeriodCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Creates a new billing/calculation period (ADMIN only)."""
    period = Period(
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="DRAFT"
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return {
        "id": period.id,
        "name": period.name,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "status": period.status
    }


@router.post("/{period_id}/calculate")
async def calculate_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Runs calculation snapshot for the period using Bitrix24 actuals and formulas (ADMIN only)."""
    period = db.query(Period).filter(Period.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Период не найден")

    try:
        res = await CalculationService.calculate_period(period_id, db)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{period_id}/lock")
def lock_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Locks the period, freezing all calculated figures and archiving it (ADMIN only)."""
    period = db.query(Period).filter(Period.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Период не найден")

    try:
        locked_p = CalculationService.lock_period(period_id, db)
        return {
            "id": locked_p.id,
            "status": locked_p.status,
            "locked_at": locked_p.locked_at.isoformat() if locked_p.locked_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{period_id}/results")
def get_period_results(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns calculation results for the period.
    Filters according to user role:
    - EMPLOYEE: sees only their own result
    - HEAD: sees subordinates in their department
    - ADMIN: sees all results
    """
    period = db.query(Period).filter(Period.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Период не найден")

    query = db.query(CalculationResult).filter(CalculationResult.period_id == period.id)

    # Role-based filtering from database user
    if current_user.role == "EMPLOYEE":
        query = query.filter(CalculationResult.user_id == current_user.id)
    elif current_user.role == "HEAD":
        if current_user.department_id:
            dept_user_ids = [
                u.id for u in db.query(User).filter(User.department_id == current_user.department_id).all()
            ]
            query = query.filter(CalculationResult.user_id.in_(dept_user_ids))
        else:
            query = query.filter(CalculationResult.user_id == current_user.id)

    results = query.all()
    out = []
    for r in results:
        emp = r.user
        out.append({
            "id": r.id,
            "user_id": r.user_id,
            "employee_name": emp.full_name if emp else "Сотрудник",
            "department_name": emp.department.name if emp and emp.department else "—",
            "position_name": emp.position.name if emp and emp.position else "—",
            "formula_expression": r.formula_expression,
            "raw_metrics": r.raw_metrics,
            "computed_variables": r.computed_variables,
            "kpi_percent": r.kpi_percent,
            "bonus_amount": r.bonus_amount,
            "total_payout": r.total_payout,
            "status": r.status,
            "notes": r.notes,
            "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None
        })
    return out
