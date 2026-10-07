"""
Bitrix24 integration service with REST API and realistic Mock Generator for client demonstrations.
"""

import os
import random
from typing import Any, Dict, List, Optional
import httpx


class BitrixAPIError(Exception):
    """Exception raised for errors during Bitrix24 API calls."""
    pass


class BitrixService:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("BITRIX_WEBHOOK_URL", "")
        self.mock_mode = os.getenv("BITRIX_MOCK_MODE", "true").lower() in ("true", "1", "yes")

    def is_configured(self) -> bool:
        return bool(self.webhook_url and not self.mock_mode)

    async def get_employee_metrics(
        self,
        bitrix_user_id: int,
        start_date: str,
        end_date: str,
        position_name: str = ""
    ) -> Dict[str, Any]:
        """
        Fetches metrics (deals, tasks, telephony) for employee for given date range.
        If mock mode is active or Bitrix is not configured, generates realistic deterministic metrics.
        """
        if self.is_configured():
            try:
                return await self._fetch_from_bitrix(bitrix_user_id, start_date, end_date)
            except Exception as e:
                # Log error and fallback to mock if API fails
                print(f"[BitrixService] Warning: API request failed: {e}. Falling back to demo data.")
                metrics = self._generate_mock_metrics(bitrix_user_id, position_name)
                metrics["warning"] = f"Bitrix24 API недоступен ({str(e)}). Использованы демонстрационные данные."
                return metrics

        return self._generate_mock_metrics(bitrix_user_id, position_name)

    async def _post_paginated(
        self,
        client: httpx.AsyncClient,
        method: str,
        payload: Dict[str, Any],
        max_pages: int = 50
    ) -> List[Any]:
        """
        Iterates over paginated Bitrix24 REST API results using start and next fields.
        Raises BitrixAPIError on response errors.
        """
        url = f"{self.webhook_url.rstrip('/')}/{method}"
        items = []
        start = 0
        pages = 0

        while pages < max_pages:
            req_payload = {**payload}
            if start > 0:
                req_payload["start"] = start

            resp = await client.post(url, json=req_payload)
            if resp.status_code >= 400:
                raise BitrixAPIError(f"Bitrix24 HTTP {resp.status_code} in {method}")

            resp_data = resp.json()
            if "error" in resp_data:
                err_msg = resp_data.get("error_description") or resp_data.get("error")
                raise BitrixAPIError(f"Bitrix24 API error in {method}: {err_msg}")

            result = resp_data.get("result")
            if isinstance(result, list):
                items.extend(result)
            elif isinstance(result, dict) and "tasks" in result:
                items.extend(result["tasks"])
            elif isinstance(result, dict):
                items.append(result)

            pages += 1
            next_offset = resp_data.get("next")
            if not next_offset:
                break
            try:
                start = int(next_offset)
            except (ValueError, TypeError):
                break

        return items

    async def _fetch_from_bitrix(
        self,
        bitrix_user_id: int,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """Queries actual Bitrix24 REST API endpoints with pagination and date formatting."""
        start_dt = f"{start_date}T00:00:00" if "T" not in start_date else start_date
        end_dt = f"{end_date}T23:59:59" if "T" not in end_date else end_date

        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Fetch Deals with pagination (all closed deals in period to compute total and conversion)
            deals_data = await self._post_paginated(
                client,
                "crm.deal.list",
                {
                    "filter": {
                        "=ASSIGNED_BY_ID": bitrix_user_id,
                        ">=CLOSEDATE": start_dt,
                        "<=CLOSEDATE": end_dt
                    },
                    "select": ["ID", "OPPORTUNITY", "STAGE_ID", "STAGE_SEMANTIC_ID"]
                }
            )
            deals_won = [
                d for d in deals_data
                if d.get("STAGE_SEMANTIC_ID") == "S" or "WON" in str(d.get("STAGE_ID", "")).upper()
            ]
            deals_won_sum = sum(float(d.get("OPPORTUNITY", 0) or 0) for d in deals_won)
            deals_won_count = len(deals_won)
            deals_total_count = len(deals_data)
            conversion_rate = (
                round((deals_won_count / deals_total_count) * 100, 1)
                if deals_total_count > 0 else 0.0
            )

            # 2. Fetch Tasks with pagination
            tasks_data = await self._post_paginated(
                client,
                "tasks.task.list",
                {
                    "filter": {
                        "=RESPONSIBLE_ID": bitrix_user_id,
                        ">=CLOSED_DATE": start_dt,
                        "<=CLOSED_DATE": end_dt
                    },
                    "select": ["ID", "STATUS", "CLOSED_DATE", "DEADLINE"]
                }
            )
            tasks_closed = len(tasks_data)

            # Check overdue tasks
            tasks_overdue = 0
            for t in tasks_data:
                deadline = t.get("deadline")
                closed = t.get("closedDate")
                if deadline and closed and closed > deadline:
                    tasks_overdue += 1

            tasks_on_time_pct = (
                round(((tasks_closed - tasks_overdue) / tasks_closed) * 100, 1)
                if tasks_closed > 0 else 100.0
            )

            return {
                "deals_won_sum": deals_won_sum,
                "deals_won_count": float(deals_won_count),
                "deals_total_count": float(deals_total_count),
                "conversion_rate": conversion_rate,
                "tasks_closed": float(tasks_closed),
                "tasks_overdue": float(tasks_overdue),
                "tasks_total": float(tasks_closed),
                "tasks_on_time_pct": tasks_on_time_pct,
                "calls_count": None,
                "calls_duration_minutes": None,
                "calls_note": "Показатель телефонии недоступен (требуется интеграция voximplant)"
            }

    def _generate_mock_metrics(self, bitrix_user_id: int, position_name: str) -> Dict[str, float]:
        """Generates realistic KPI indicators suited for specific roles."""
        # Use user_id as seed for consistent reproducible demo numbers
        rnd = random.Random(bitrix_user_id * 31 + 7)

        pos_lower = position_name.lower()
        if "продаж" in pos_lower or "sales" in pos_lower or "коммерческ" in pos_lower:
            # Sales role: High deal volume, moderate tasks
            deals_won_sum = rnd.randint(310, 680) * 1000.0  # 310,000 - 680,000 ₽
            deals_won_count = rnd.randint(8, 22)
            deals_total_count = deals_won_count + rnd.randint(5, 15)
            conv = round((deals_won_count / deals_total_count) * 100, 1)
            tasks_closed = rnd.randint(15, 28)
            tasks_overdue = rnd.choice([0, 0, 1, 2])
            calls_count = rnd.randint(110, 240)
            calls_duration = rnd.randint(220, 520)
        elif "разработ" in pos_lower or "инженер" in pos_lower or "dev" in pos_lower:
            # Development / Engineering role: High task focus, no direct CRM sales
            deals_won_sum = 0.0
            deals_won_count = 0.0
            deals_total_count = 0.0
            conv = 0.0
            tasks_closed = rnd.randint(24, 45)
            tasks_overdue = rnd.choice([0, 0, 1, 1, 2])
            calls_count = rnd.randint(10, 30)
            calls_duration = rnd.randint(30, 90)
        else:
            # General / Support role
            deals_won_sum = rnd.randint(50, 200) * 1000.0
            deals_won_count = rnd.randint(3, 8)
            deals_total_count = deals_won_count + 3
            conv = 65.0
            tasks_closed = rnd.randint(20, 35)
            tasks_overdue = rnd.choice([0, 1])
            calls_count = rnd.randint(80, 160)
            calls_duration = rnd.randint(150, 350)

        tasks_total = tasks_closed + rnd.randint(1, 4)
        on_time = max(0, tasks_closed - tasks_overdue)
        on_time_pct = round((on_time / tasks_closed) * 100, 1) if tasks_closed > 0 else 100.0

        return {
            "deals_won_sum": float(deals_won_sum),
            "deals_won_count": float(deals_won_count),
            "deals_total_count": float(deals_total_count),
            "conversion_rate": float(conv),
            "tasks_closed": float(tasks_closed),
            "tasks_overdue": float(tasks_overdue),
            "tasks_total": float(tasks_total),
            "tasks_on_time_pct": float(on_time_pct),
            "calls_count": float(calls_count),
            "calls_duration_minutes": float(calls_duration)
        }


# Singleton service instance
bitrix_service = BitrixService()
