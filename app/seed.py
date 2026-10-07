"""
Initial seed data generator for realistic demo and turnkey client presentation.
"""

from sqlalchemy.orm import Session
from app.models.entities import Department, Position, FormulaTemplate, User, Period, EmployeeTarget


def seed_database(db: Session):
    """Fills the database with initial company structure, positions, formulas and users."""
    if db.query(Department).first():
        return  # Already seeded

    print("[Seed] Populating initial company structure and formulas...")

    # 1. Departments
    dept_sales = Department(name="Отдел продаж", description="Работа с клиентами, воронка CRM и выполнение плана выручки")
    dept_it = Department(name="Отдел разработки и IT", description="Разработка платформы, архитектура и закрытие спринтов")
    dept_support = Department(name="Клиентский сервис", description="Первая линия поддержки, обработка обращений и звонки")
    db.add_all([dept_sales, dept_it, dept_support])
    db.commit()

    # 2. Positions & Formula Templates
    pos_sales = Position(department_id=dept_sales.id, name="Менеджер по продажам")
    pos_rop = Position(department_id=dept_sales.id, name="Руководитель отдела продаж (РОП)")
    pos_dev = Position(department_id=dept_it.id, name="Senior Backend Developer")
    pos_support = Position(department_id=dept_support.id, name="Специалист техподдержки")
    db.add_all([pos_sales, pos_rop, pos_dev, pos_support])
    db.commit()

    f1 = FormulaTemplate(
        position_id=pos_sales.id,
        name="KPI Менеджера по продажам",
        formula_expression="IF(deals_won_sum >= plan_sales, base_rate * 0.7 * (deals_won_sum / plan_sales), base_rate * 0.4 * (deals_won_sum / plan_sales))",
        description="При выполнении плана продаж — премия 70% от оклада с коэффициентом перевыполнения. При недовыполнении — пониженный коэффициент 40%."
    )
    f2 = FormulaTemplate(
        position_id=pos_rop.id,
        name="KPI Руководителя отдела продаж",
        formula_expression="base_rate * 0.5 * (deals_won_sum / plan_sales) + IF(tasks_on_time_pct >= 90, 15000, 0)",
        description="Бонус за общий объем выручки отдела + фиксированная надбавка 15 000 ₽ при своевременном закрытии задач отдела от 90%."
    )
    f3 = FormulaTemplate(
        position_id=pos_dev.id,
        name="KPI Разработчика (Sprint Performance)",
        formula_expression="IF(AND(tasks_closed >= plan_tasks, tasks_overdue == 0), base_rate * 0.35, base_rate * 0.2 * (tasks_closed / plan_tasks))",
        description="35% премия при выполнении плана задач без единой просрочки. При наличии просрочек — пропорционально закрытым задачам со ставкой 20%."
    )
    f4 = FormulaTemplate(
        position_id=pos_support.id,
        name="KPI Специалиста поддержки (SLA и Звонки)",
        formula_expression="ROUND(base_rate * 0.3 * (calls_count / target_calls) * (quality_score / 100), 2)",
        description="Премия 30% от оклада, умноженная на процент выполнения нормы звонков и коэффициент оценки качества сервиса (1-100)."
    )
    db.add_all([f1, f2, f3, f4])
    db.commit()

    # 3. Users
    u_admin = User(
        email="admin@company.ru",
        full_name="Алексей Смирнов",
        role="ADMIN",
        department_id=dept_sales.id,
        position_id=None,
        bitrix_user_id=1,
        avatar_url="/static/img/avatar.svg"
    )
    u_rop = User(
        email="voronov@company.ru",
        full_name="Михаил Воронов",
        role="HEAD",
        department_id=dept_sales.id,
        position_id=pos_rop.id,
        bitrix_user_id=2,
        avatar_url="/static/img/avatar.svg"
    )
    u_sales1 = User(
        email="sokolov@company.ru",
        full_name="Дмитрий Соколов",
        role="EMPLOYEE",
        department_id=dept_sales.id,
        position_id=pos_sales.id,
        bitrix_user_id=3,
        avatar_url="/static/img/avatar.svg"
    )
    u_sales2 = User(
        email="kuznetsova@company.ru",
        full_name="Елена Кузнецова",
        role="EMPLOYEE",
        department_id=dept_sales.id,
        position_id=pos_sales.id,
        bitrix_user_id=4,
        avatar_url="/static/img/avatar.svg"
    )
    u_dev1 = User(
        email="vasiliev@company.ru",
        full_name="Артем Васильев",
        role="EMPLOYEE",
        department_id=dept_it.id,
        position_id=pos_dev.id,
        bitrix_user_id=5,
        avatar_url="/static/img/avatar.svg"
    )
    u_supp1 = User(
        email="morozova@company.ru",
        full_name="Анна Морозова",
        role="EMPLOYEE",
        department_id=dept_support.id,
        position_id=pos_support.id,
        bitrix_user_id=6,
        avatar_url="/static/img/avatar.svg"
    )
    db.add_all([u_admin, u_rop, u_sales1, u_sales2, u_dev1, u_supp1])
    db.commit()

    # 4. Reporting Periods
    p_sept = Period(
        name="Сентябрь 2026",
        start_date="2026-09-01",
        end_date="2026-09-30",
        status="DRAFT"
    )
    p_oct = Period(
        name="Октябрь 2026",
        start_date="2026-10-01",
        end_date="2026-10-31",
        status="DRAFT"
    )
    db.add_all([p_sept, p_oct])
    db.commit()

    # 5. Individual targets for both demo periods (same plan per role in each period)
    target_templates = [
        (u_rop, 90000.0, 1200000.0, 30.0, 80.0, 95.0),
        (u_sales1, 55000.0, 450000.0, 20.0, 150.0, 90.0),
        (u_sales2, 50000.0, 400000.0, 20.0, 150.0, 95.0),
        (u_dev1, 140000.0, 0.0, 30.0, 20.0, 100.0),
        (u_supp1, 48000.0, 0.0, 25.0, 140.0, 98.0),
    ]
    for period in (p_sept, p_oct):
        for user, base_rate, plan_sales, plan_tasks, target_calls, quality_score in target_templates:
            db.add(EmployeeTarget(
                period_id=period.id,
                user_id=user.id,
                base_rate=base_rate,
                plan_sales=plan_sales,
                plan_tasks=plan_tasks,
                target_calls=target_calls,
                quality_score=quality_score
            ))
    db.commit()

    print("[Seed] Database successfully initialized with demo structure.")
