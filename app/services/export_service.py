"""
Export Service: generates styled Excel (.xlsx) workbooks and CSV files using openpyxl.
"""

import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.models.entities import Period, CalculationResult


class ExportService:

    @staticmethod
    def export_period_excel(period_id: int, db: Session) -> io.BytesIO:
        """
        Builds a professionally styled Excel spreadsheet with formulas,
        KPI breakdown, conditional styling and totals.
        """
        period = db.query(Period).filter(Period.id == period_id).first()
        if not period:
            raise ValueError("Период не найден")

        results = db.query(CalculationResult).filter(
            CalculationResult.period_id == period.id
        ).all()

        wb = Workbook()
        ws = wb.active
        ws.title = "Ведомость KPI"
        ws.views.sheetView[0].showGridLines = True

        # Styles
        title_font = Font(name="Calibri", size=16, bold=True, color="1E293B")
        sub_font = Font(name="Calibri", size=11, italic=True, color="64748B")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        
        green_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        yellow_fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
        red_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

        total_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
        total_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        # Title Block
        ws.merge_cells("A1:M1")
        ws["A1"] = f"Ведомость расчета эффективности и начисления премий (KPI)"
        ws["A1"].font = title_font
        ws["A1"].alignment = Alignment(vertical="center")

        status_text = "ЗАФИКСИРОВАН (Архив)" if period.status == "LOCKED" else "ПРЕДВАРИТЕЛЬНЫЙ РАСЧЕТ"
        ws.merge_cells("A2:M2")
        ws["A2"] = f"Отчетный период: {period.name} ({period.start_date} — {period.end_date}) | Статус: {status_text}"
        ws["A2"].font = sub_font
        ws["A2"].alignment = Alignment(vertical="center")

        ws.row_dimensions[1].height = 28
        ws.row_dimensions[2].height = 20
        ws.row_dimensions[4].height = 26

        # Headers
        headers = [
            "№", "Сотрудник", "Отдел", "Должность",
            "Оклад, ₽", "План продаж, ₽", "Факт выручки, ₽",
            "Закрыто задач", "% в срок",
            "Формула расчета", "KPI, %", "Премия, ₽", "Итого к выплате, ₽"
        ]

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

        # Data rows
        start_row = 5
        curr_row = start_row

        for idx, res in enumerate(results, 1):
            emp = res.user
            dept_name = emp.department.name if emp and emp.department else "—"
            pos_name = emp.position.name if emp and emp.position else "—"

            ctx = res.computed_variables
            base_rate = ctx.get("base_rate", 0.0)
            plan_sales = ctx.get("plan_sales", 0.0)
            fact_sales = ctx.get("deals_won_sum", 0.0)
            tasks_closed = ctx.get("tasks_closed", 0.0)
            tasks_on_time = ctx.get("tasks_on_time_pct", 100.0)

            ws.cell(row=curr_row, column=1, value=idx).alignment = Alignment(horizontal="center")
            ws.cell(row=curr_row, column=2, value=emp.full_name if emp else "Сотрудник")
            ws.cell(row=curr_row, column=3, value=dept_name)
            ws.cell(row=curr_row, column=4, value=pos_name)

            c5 = ws.cell(row=curr_row, column=5, value=base_rate)
            c5.number_format = '#,##0 ₽'

            c6 = ws.cell(row=curr_row, column=6, value=plan_sales)
            c6.number_format = '#,##0 ₽'

            c7 = ws.cell(row=curr_row, column=7, value=fact_sales)
            c7.number_format = '#,##0 ₽'

            ws.cell(row=curr_row, column=8, value=tasks_closed).alignment = Alignment(horizontal="center")
            
            c9 = ws.cell(row=curr_row, column=9, value=tasks_on_time / 100.0)
            c9.number_format = '0.0%'
            c9.alignment = Alignment(horizontal="center")

            ws.cell(row=curr_row, column=10, value=res.formula_expression)

            # KPI % with color highlight
            c11 = ws.cell(row=curr_row, column=11, value=res.kpi_percent / 100.0)
            c11.number_format = '0.0%'
            c11.alignment = Alignment(horizontal="center")
            if res.kpi_percent >= 100:
                c11.fill = green_fill
            elif res.kpi_percent >= 80:
                c11.fill = yellow_fill
            else:
                c11.fill = red_fill

            c12 = ws.cell(row=curr_row, column=12, value=res.bonus_amount)
            c12.number_format = '#,##0 ₽'

            c13 = ws.cell(row=curr_row, column=13, value=res.total_payout)
            c13.number_format = '#,##0 ₽'
            c13.font = Font(bold=True)

            for c in range(1, 14):
                ws.cell(row=curr_row, column=c).border = thin_border

            ws.row_dimensions[curr_row].height = 22
            curr_row += 1

        # Totals Row
        if results:
            ws.merge_cells(f"A{curr_row}:D{curr_row}")
            total_lbl = ws.cell(row=curr_row, column=1, value="ИТОГО ПО КОМПАНИИ:")
            total_lbl.font = total_font
            total_lbl.fill = total_fill
            total_lbl.alignment = Alignment(horizontal="right", vertical="center")

            # Sum of Base Salaries
            t_base = ws.cell(row=curr_row, column=5, value=f"=SUM(E{start_row}:E{curr_row-1})")
            t_base.font = total_font
            t_base.fill = total_fill
            t_base.number_format = '#,##0 ₽'

            # Sum of Planned Sales
            t_ps = ws.cell(row=curr_row, column=6, value=f"=SUM(F{start_row}:F{curr_row-1})")
            t_ps.font = total_font
            t_ps.fill = total_fill
            t_ps.number_format = '#,##0 ₽'

            # Sum of Actual Sales
            t_fs = ws.cell(row=curr_row, column=7, value=f"=SUM(G{start_row}:G{curr_row-1})")
            t_fs.font = total_font
            t_fs.fill = total_fill
            t_fs.number_format = '#,##0 ₽'

            # Empty for tasks/formula
            for c in range(8, 12):
                ws.cell(row=curr_row, column=c).fill = total_fill

            # Sum of Bonus
            t_b = ws.cell(row=curr_row, column=12, value=f"=SUM(L{start_row}:L{curr_row-1})")
            t_b.font = total_font
            t_b.fill = total_fill
            t_b.number_format = '#,##0 ₽'

            # Sum of Payout
            t_pay = ws.cell(row=curr_row, column=13, value=f"=SUM(M{start_row}:M{curr_row-1})")
            t_pay.font = total_font
            t_pay.fill = total_fill
            t_pay.number_format = '#,##0 ₽'

            for c in range(1, 14):
                ws.cell(row=curr_row, column=c).border = thin_border

            ws.row_dimensions[curr_row].height = 24

        # Auto-adjust column widths
        col_widths = {1: 6, 2: 24, 3: 20, 4: 22, 5: 16, 6: 16, 7: 18, 8: 14, 9: 12, 10: 34, 11: 12, 12: 16, 13: 18}
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
