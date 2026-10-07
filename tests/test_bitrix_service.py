import pytest
import httpx
from unittest.mock import patch

from app.services.bitrix_service import BitrixService, BitrixAPIError


@pytest.mark.anyio
async def test_bitrix_pagination_sums_multiple_pages():
    service = BitrixService(webhook_url="https://portal.bitrix24.ru/rest/1/validtoken")
    service.mock_mode = False

    deal_page_1 = {
        "result": [
            {"ID": "1", "OPPORTUNITY": "150000", "STAGE_ID": "WON"},
            {"ID": "2", "OPPORTUNITY": "50000", "STAGE_ID": "WON"},
        ],
        "next": 2,
        "total": 3
    }
    deal_page_2 = {
        "result": [
            {"ID": "3", "OPPORTUNITY": "75000", "STAGE_ID": "WON"},
        ],
        "total": 3
    }

    tasks_page = {
        "result": {
            "tasks": [
                {"id": "10", "status": "5", "closedDate": "2026-10-10", "deadline": "2026-10-15"},
                {"id": "11", "status": "5", "closedDate": "2026-10-20", "deadline": "2026-10-18"}  # overdue
            ]
        },
        "total": 2
    }

    async def mock_post(url, json=None):
        if "crm.deal.list" in url:
            if not json or "start" not in json:
                return httpx.Response(200, json=deal_page_1)
            elif json.get("start") == 2:
                return httpx.Response(200, json=deal_page_2)
        elif "tasks.task.list" in url:
            return httpx.Response(200, json=tasks_page)
        return httpx.Response(404)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        metrics = await service._fetch_from_bitrix(1, "2026-10-01", "2026-10-31")

    # 150000 + 50000 + 75000 = 275000
    assert metrics["deals_won_sum"] == 275000.0
    assert metrics["deals_won_count"] == 3.0
    assert metrics["deals_total_count"] == 3.0
    assert metrics["conversion_rate"] == 100.0
    assert metrics["tasks_closed"] == 2.0
    assert metrics["tasks_overdue"] == 1.0
    assert metrics["tasks_total"] == 2.0


@pytest.mark.anyio
async def test_bitrix_conversion_rate_calculated_from_real_deal_counts():
    service = BitrixService(webhook_url="https://portal.bitrix24.ru/rest/1/validtoken")
    service.mock_mode = False

    # 4 deals total: 2 WON, 2 LOSE/IN_PROGRESS
    deals_page = {
        "result": [
            {"ID": "1", "OPPORTUNITY": "100000", "STAGE_ID": "WON", "STAGE_SEMANTIC_ID": "S"},
            {"ID": "2", "OPPORTUNITY": "50000", "STAGE_ID": "LOSE", "STAGE_SEMANTIC_ID": "F"},
            {"ID": "3", "OPPORTUNITY": "200000", "STAGE_ID": "WON", "STAGE_SEMANTIC_ID": "S"},
            {"ID": "4", "OPPORTUNITY": "30000", "STAGE_ID": "EXECUTING", "STAGE_SEMANTIC_ID": "P"},
        ],
        "total": 4
    }
    empty_tasks = {"result": {"tasks": []}, "total": 0}

    async def mock_post(url, json=None):
        if "crm.deal.list" in url:
            return httpx.Response(200, json=deals_page)
        return httpx.Response(200, json=empty_tasks)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        metrics = await service._fetch_from_bitrix(1, "2026-10-01", "2026-10-31")

    assert metrics["deals_total_count"] == 4.0
    assert metrics["deals_won_count"] == 2.0
    assert metrics["deals_won_sum"] == 300000.0
    assert metrics["conversion_rate"] == 50.0
    assert metrics["tasks_total"] == 0.0


@pytest.mark.anyio
async def test_bitrix_api_error_handling_raises_and_warns():
    service = BitrixService(webhook_url="https://portal.bitrix24.ru/rest/1/validtoken")
    service.mock_mode = False

    error_response = {
        "error": "INVALID_CREDENTIALS",
        "error_description": "The webhook token is invalid or expired"
    }

    async def mock_post_error(url, json=None):
        return httpx.Response(200, json=error_response)

    with patch("httpx.AsyncClient.post", side_effect=mock_post_error):
        # 1. Direct call raises BitrixAPIError with description
        with pytest.raises(BitrixAPIError, match="The webhook token is invalid or expired"):
            await service._fetch_from_bitrix(1, "2026-10-01", "2026-10-31")

        # 2. get_employee_metrics gracefully falls back to mock with warning
        metrics = await service.get_employee_metrics(1, "2026-10-01", "2026-10-31", "Менеджер")
        assert "warning" in metrics
        assert "The webhook token is invalid or expired" in metrics["warning"]


@pytest.mark.anyio
async def test_telephony_metrics_are_not_fake_constants():
    service = BitrixService(webhook_url="https://portal.bitrix24.ru/rest/1/validtoken")
    service.mock_mode = False

    empty_deal = {"result": [], "total": 0}
    empty_tasks = {"result": {"tasks": []}, "total": 0}

    async def mock_post_empty(url, json=None):
        if "crm.deal.list" in url:
            return httpx.Response(200, json=empty_deal)
        return httpx.Response(200, json=empty_tasks)

    with patch("httpx.AsyncClient.post", side_effect=mock_post_empty):
        metrics = await service._fetch_from_bitrix(1, "2026-10-01", "2026-10-31")

    # In live mode without telephony integration, calls_count must be None (not hardcoded 100.0)
    assert metrics["calls_count"] is None
    assert metrics["calls_duration_minutes"] is None
    assert "calls_note" in metrics


@pytest.mark.anyio
async def test_bitrix_date_formatting_includes_timestamps():
    service = BitrixService(webhook_url="https://portal.bitrix24.ru/rest/1/validtoken")
    service.mock_mode = False

    captured_filters = []

    async def mock_post_capture(url, json=None):
        captured_filters.append(json.get("filter", {}))
        return httpx.Response(200, json={"result": [], "total": 0})

    with patch("httpx.AsyncClient.post", side_effect=mock_post_capture):
        await service._fetch_from_bitrix(1, "2026-10-01", "2026-10-31")

    # Filter dates must have T00:00:00 and T23:59:59
    assert len(captured_filters) == 2
    deal_filter = captured_filters[0]
    assert deal_filter[">=CLOSEDATE"] == "2026-10-01T00:00:00"
    assert deal_filter["<=CLOSEDATE"] == "2026-10-31T23:59:59"

    task_filter = captured_filters[1]
    assert task_filter[">=CLOSED_DATE"] == "2026-10-01T00:00:00"
    assert task_filter["<=CLOSED_DATE"] == "2026-10-31T23:59:59"
