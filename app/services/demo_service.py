"""
Прогрев демонстрационных данных.

При первом запуске в демонстрационном режиме самый свежий период рассчитывается
автоматически, чтобы дашборд сразу показывал данные, а не пустое состояние.
В live-режиме (реальный портал Битрикс24) прогрев не выполняется: стартовых
запросов к внешнему API не делаем.
"""

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.entities import CalculationResult, Period
from app.services.bitrix_service import bitrix_service
from app.services.calculation_service import CalculationService


async def warmup_demo_data(db: Session) -> Optional[Dict[str, Any]]:
    """
    Считает последний незафиксированный период, если по нему ещё нет результатов.
    Возвращает результат расчета либо None, если прогрев не требовался.
    """
    if not bitrix_service.mock_mode:
        return None

    period = db.query(Period).order_by(Period.id.desc()).first()
    if not period or period.status == "LOCKED":
        return None

    has_results = db.query(CalculationResult).filter(
        CalculationResult.period_id == period.id
    ).first()
    if has_results:
        return None

    return await CalculationService.calculate_period(period.id, db)
