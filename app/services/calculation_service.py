"""
Calculation service coordinating the KPI pipeline:
Bitrix24 metrics -> Formula Engine -> Persistent Calculation Results & History.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from app.models.entities import Period, User, CalculationResult, EmployeeTarget
from app.services.formula_engine import FormulaEngine, FormulaError
from app.services.bitrix_service import bitrix_service


class CalculationService:

    @staticmethod
    async def calculate_period(period_id: int, db: Session) -> Dict[str, Any]:
        """
        Executes snapshot calculation for all eligible employees in the period:
        1. Checks lock state
        2. Gathers actual metrics from Bitrix24
        3. Retrieves individual targets
        4. Evaluates position formula
        5. Saves/updates CalculationResult records
        Wrapped in try/except with db.rollback() on unexpected errors.
        """
        period = db.query(Period).filter(Period.id == period_id).first()
        if not period:
            raise ValueError(f"Период #{period_id} не найден")

        if period.status == "LOCKED":
            raise ValueError("Расчет заблокирован: период уже зафиксирован и закрыт для изменений")

        warnings: List[str] = []

        try:
            # Fetch all employees with assigned positions
            employees = db.query(User).filter(
                User.position_id.isnot(None),
                User.role.in_(["EMPLOYEE", "HEAD"])
            ).all()

            results_created = 0

            for emp in employees:
                pos = emp.position
                formula_tpl = pos.formula_template if pos else None
                
                # Default fallback formula if position has no custom formula
                expr = (
                    formula_tpl.formula_expression
                    if formula_tpl and formula_tpl.formula_expression
                    else "IF(deals_won_sum >= plan_sales, base_rate * 0.5, base_rate * 0.5 * (deals_won_sum / plan_sales))"
                )

                # 1. Individual Target
                target = db.query(EmployeeTarget).filter(
                    EmployeeTarget.period_id == period.id,
                    EmployeeTarget.user_id == emp.id
                ).first()

                if not target:
                    warnings.append(f"У сотрудника {emp.full_name} нет индивидуального плана на период — использованы значения по умолчанию")

                base_rate = target.base_rate if target else 50000.0
                plan_sales = target.plan_sales if target else 300000.0
                plan_tasks = target.plan_tasks if target else 20.0
                target_calls = target.target_calls if target else 100.0
                quality_score = target.quality_score if target else 100.0

                # 2. Actual metrics from Bitrix24
                bitrix_uid = emp.bitrix_user_id or emp.id
                actual_metrics = await bitrix_service.get_employee_metrics(
                    bitrix_user_id=bitrix_uid,
                    start_date=period.start_date,
                    end_date=period.end_date,
                    position_name=pos.name if pos else ""
                )

                if "warning" in actual_metrics:
                    warnings.append(f"Сотрудник {emp.full_name}: {actual_metrics['warning']}")

                # 3. Build unified evaluation context
                context = {
                    **actual_metrics,
                    "base_rate": base_rate,
                    "plan_sales": plan_sales,
                    "plan_tasks": plan_tasks,
                    "target_calls": target_calls,
                    "quality_score": quality_score,
                }

                # 4. Evaluate formula
                calc_status = "CALCULATED"
                try:
                    computed_bonus = FormulaEngine.evaluate(expr, context)
                except FormulaError as e:
                    computed_bonus = 0.0
                    notes = f"Ошибка формулы: {str(e)}"
                    calc_status = "ERROR"
                    warnings.append(f"У сотрудника {emp.full_name} ошибка формулы: {str(e)}")
                else:
                    notes = "Расчет выполнен успешно"

                # KPI percentage (relative to planned bonus or plan performance)
                fact_sales = float(actual_metrics.get("deals_won_sum", 0.0) or 0.0)
                fact_tasks = float(actual_metrics.get("tasks_closed", 0.0) or 0.0)

                if plan_sales > 0:
                    kpi_pct = round(fact_sales / plan_sales * 100, 1)
                elif plan_tasks > 0:
                    kpi_pct = round(fact_tasks / plan_tasks * 100, 1)
                else:
                    kpi_pct = 0.0

                total_payout = round(base_rate + computed_bonus, 2)

                # 5. Persist or update CalculationResult
                calc_record = db.query(CalculationResult).filter(
                    CalculationResult.period_id == period.id,
                    CalculationResult.user_id == emp.id
                ).first()

                if not calc_record:
                    calc_record = CalculationResult(
                        period_id=period.id,
                        user_id=emp.id,
                        formula_template_id=formula_tpl.id if formula_tpl else None,
                    )
                    db.add(calc_record)

                calc_record.formula_expression = expr
                calc_record.raw_metrics = actual_metrics
                calc_record.computed_variables = context
                calc_record.kpi_percent = kpi_pct
                calc_record.bonus_amount = round(computed_bonus, 2)
                calc_record.total_payout = total_payout
                calc_record.notes = notes
                calc_record.calculated_at = datetime.now(timezone.utc)
                calc_record.status = calc_status

                results_created += 1

            if results_created > 0:
                period.status = "CALCULATED"
            db.commit()

            return {
                "period_id": period.id,
                "period_name": period.name,
                "status": period.status,
                "employees_calculated": results_created,
                "warnings": warnings
            }
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def lock_period(period_id: int, db: Session) -> Period:
        """Locks period, freezing all calculated numbers forever."""
        period = db.query(Period).filter(Period.id == period_id).first()
        if not period:
            raise ValueError(f"Период #{period_id} не найден")
        
        period.status = "LOCKED"
        period.locked_at = datetime.now(timezone.utc)

        # Update status of results
        db.query(CalculationResult).filter(
            CalculationResult.period_id == period.id
        ).update({"status": "LOCKED"})

        db.commit()
        db.refresh(period)
        return period
