"""
API router for Formula Editor, Sandbox live-testing, and Position Formula Templates.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.entities import FormulaTemplate, Position, User
from app.schemas.schemas import FormulaTestRequest, FormulaTemplateUpdate
from app.services.formula_engine import FormulaEngine
from app.api.deps import require_admin, get_current_user

router = APIRouter(prefix="/api/formulas", tags=["Formulas"])


@router.get("/variables")
def get_formula_variables():
    """Returns available variables catalog for autocomplete in the editor."""
    return FormulaEngine.get_catalog()


@router.post("/sandbox/test")
def test_formula_in_sandbox(
    payload: FormulaTestRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Evaluates formula in safe sandbox.
    Returns syntax validity, computed result, used variables and substituted numbers.
    """
    result = FormulaEngine.test_sandbox(payload.expression, payload.custom_variables)
    return result


@router.get("/templates")
def list_formula_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists all formula templates mapped to positions."""
    templates = db.query(FormulaTemplate).all()
    out = []
    for t in templates:
        out.append({
            "id": t.id,
            "position_id": t.position_id,
            "position_name": t.position.name if t.position else None,
            "department_name": t.position.department.name if t.position and t.position.department else None,
            "name": t.name,
            "formula_expression": t.formula_expression,
            "description": t.description,
            "is_active": t.is_active,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None
        })
    return out


@router.put("/templates/{position_id}")
def update_position_formula(
    position_id: int,
    payload: FormulaTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Saves or updates formula expression for a given position."""
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Должность не найдена")

    # Validate formula before saving
    if payload.formula_expression:
        test_res = FormulaEngine.test_sandbox(payload.formula_expression)
        if not test_res["valid"]:
            raise HTTPException(status_code=400, detail=f"Ошибка в формуле: {test_res['error']}")

    tpl = db.query(FormulaTemplate).filter(FormulaTemplate.position_id == position_id).first()
    if not tpl:
        tpl = FormulaTemplate(
            position_id=position_id,
            name=payload.name or f"Формула KPI: {pos.name}",
            formula_expression=payload.formula_expression or "base_rate",
            description=payload.description
        )
        db.add(tpl)
    else:
        if payload.name:
            tpl.name = payload.name
        if payload.formula_expression:
            tpl.formula_expression = payload.formula_expression
        if payload.description is not None:
            tpl.description = payload.description

    db.commit()
    db.refresh(tpl)

    return {
        "id": tpl.id,
        "position_id": tpl.position_id,
        "name": tpl.name,
        "formula_expression": tpl.formula_expression,
        "description": tpl.description
    }
