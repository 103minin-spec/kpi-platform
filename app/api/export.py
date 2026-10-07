"""
API router for Exporting calculation results to Excel and CSV.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from urllib.parse import quote
import io
import csv

from app.database import get_db
from app.models.entities import Period, CalculationResult, User
from app.services.export_service import ExportService
from app.api.deps import require_head_or_admin

router = APIRouter(prefix="/api/export", tags=["Export"])


@router.get("/periods/{period_id}/excel")
def download_excel(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_head_or_admin)
):
    """Generates and streams an itemized Excel workbook with formatting and formulas."""
    period = db.query(Period).filter(Period.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Период не найден")

    try:
        excel_stream = ExportService.export_period_excel(period_id, db)
        period_name = period.name or f"period_{period_id}"
        encoded_name = quote(period_name.encode("utf-8"))

        return StreamingResponse(
            excel_stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="KPI_Report_period_{period_id}.xlsx"; filename*=UTF-8\'\'KPI_Report_{encoded_name}.xlsx'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации Excel: {str(e)}")


@router.get("/periods/{period_id}/csv")
def download_csv(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_head_or_admin)
):
    """Exports CSV formatted with UTF-8-SIG for instant compatibility with Russian Excel/1C."""
    period = db.query(Period).filter(Period.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Период не найден")

    try:
        results = db.query(CalculationResult).filter(CalculationResult.period_id == period.id).all()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            "ID", "Сотрудник", "Отдел", "Должность",
            "Оклад", "План продаж", "Факт продаж", "Закрыто задач",
            "% вовремя", "Формула", "KPI %", "Премия", "Итого к выплате"
        ])

        for r in results:
            emp = r.user
            ctx = r.computed_variables
            writer.writerow([
                r.id,
                emp.full_name if emp else "",
                emp.department.name if emp and emp.department else "",
                emp.position.name if emp and emp.position else "",
                ctx.get("base_rate", 0),
                ctx.get("plan_sales", 0),
                ctx.get("deals_won_sum", 0),
                ctx.get("tasks_closed", 0),
                ctx.get("tasks_on_time_pct", 100),
                r.formula_expression,
                f"{r.kpi_percent}%",
                r.bonus_amount,
                r.total_payout
            ])

        csv_bytes = output.getvalue().encode('utf-8-sig')
        stream = io.BytesIO(csv_bytes)
        period_name = period.name or f"period_{period_id}"
        encoded_name = quote(period_name.encode("utf-8"))

        return StreamingResponse(
            stream,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="kpi_report_{period_id}.csv"; filename*=UTF-8\'\'kpi_{encoded_name}.csv'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации CSV: {str(e)}")
