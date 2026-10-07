"""
API router for Organizational Structure (Departments, Positions, Employees, Targets).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Department, Position, User, EmployeeTarget, Period
from app.schemas.schemas import TargetUpdate
from app.api.deps import get_current_user, require_head_or_admin

router = APIRouter(prefix="/api/company", tags=["Company"])


@router.get("/structure")
def get_company_structure(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_head_or_admin)
):
    """Returns organizational hierarchy: departments, positions, formula status, employees."""
    departments = db.query(Department).all()
    res = []
    for d in departments:
        pos_list = []
        for p in d.positions:
            emp_list = []
            for u in p.users:
                emp_list.append({
                    "id": u.id,
                    "full_name": u.full_name,
                    "email": u.email,
                    "role": u.role,
                    "bitrix_user_id": u.bitrix_user_id
                })
            
            formula_info = None
            if p.formula_template:
                formula_info = {
                    "id": p.formula_template.id,
                    "name": p.formula_template.name,
                    "expression": p.formula_template.formula_expression,
                    "description": p.formula_template.description
                }

            pos_list.append({
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "formula": formula_info,
                "employees": emp_list
            })
        
        res.append({
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "positions": pos_list
        })
    return res


@router.get("/employees")
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_head_or_admin)
):
    """Returns flat list of employees with their department and position."""
    users = db.query(User).filter(User.role.in_(["EMPLOYEE", "HEAD"])).all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "department_id": u.department_id,
            "department_name": u.department.name if u.department else "—",
            "position_id": u.position_id,
            "position_name": u.position.name if u.position else "—",
            "bitrix_user_id": u.bitrix_user_id
        })
    return out


@router.get("/periods/{period_id}/targets")
def get_period_targets(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_head_or_admin)
):
    """Returns individual targets for each employee for the given period."""
    period = db.query(Period).filter(Period.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Период не найден")

    users_query = db.query(User).filter(User.role.in_(["EMPLOYEE", "HEAD"]))
    if current_user.role == "HEAD" and current_user.department_id:
        users_query = users_query.filter(User.department_id == current_user.department_id)

    users = users_query.all()
    out = []
    for u in users:
        target = db.query(EmployeeTarget).filter(
            EmployeeTarget.period_id == period.id,
            EmployeeTarget.user_id == u.id
        ).first()

        out.append({
            "user_id": u.id,
            "full_name": u.full_name,
            "department_name": u.department.name if u.department else "—",
            "position_name": u.position.name if u.position else "—",
            "base_rate": target.base_rate if target else 50000.0,
            "plan_sales": target.plan_sales if target else 300000.0,
            "plan_tasks": target.plan_tasks if target else 20.0,
            "target_calls": target.target_calls if target else 100.0,
            "quality_score": target.quality_score if target else 100.0
        })
    return out


@router.put("/periods/{period_id}/targets/{user_id}")
def update_employee_target(
    period_id: int,
    user_id: int,
    payload: TargetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sets individual target thresholds for an employee in a given period."""
    period = db.query(Period).filter(Period.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Период не найден")

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    if current_user.role == "ADMIN":
        pass
    elif current_user.role == "HEAD":
        if target_user.department_id != current_user.department_id:
            raise HTTPException(
                status_code=403,
                detail="Доступ запрещен: руководитель может менять планы только сотрудников своего отдела"
            )
    else:
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещен: недостаточно прав для редактирования планов"
        )

    target = db.query(EmployeeTarget).filter(
        EmployeeTarget.period_id == period_id,
        EmployeeTarget.user_id == user_id
    ).first()

    if not target:
        target = EmployeeTarget(
            period_id=period_id,
            user_id=user_id,
            base_rate=payload.base_rate,
            plan_sales=payload.plan_sales,
            plan_tasks=payload.plan_tasks,
            target_calls=payload.target_calls,
            quality_score=payload.quality_score
        )
        db.add(target)
    else:
        target.base_rate = payload.base_rate
        target.plan_sales = payload.plan_sales
        target.plan_tasks = payload.plan_tasks
        target.target_calls = payload.target_calls
        target.quality_score = payload.quality_score

    db.commit()
    db.refresh(target)
    return {"status": "ok", "user_id": user_id, "period_id": period_id}
