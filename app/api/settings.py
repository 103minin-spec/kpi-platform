"""
API router for application and Bitrix24 settings.
"""

import time
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User
from app.schemas.schemas import BitrixSettingsUpdate
from app.services.bitrix_service import bitrix_service
from app.services.settings_service import SettingsService
from app.api.deps import require_admin

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("/bitrix")
def get_bitrix_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Returns Bitrix24 settings with masked webhook URL (ADMIN only)."""
    return {
        "mock_mode": bitrix_service.mock_mode,
        "is_configured": bitrix_service.is_configured(),
        "webhook_url_masked": SettingsService.mask_webhook_url(bitrix_service.webhook_url)
    }


@router.put("/bitrix")
def update_bitrix_settings(
    payload: BitrixSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Updates Bitrix24 webhook URL and mock mode in DB and runtime (ADMIN only)."""
    if payload.clear_webhook:
        SettingsService.set_setting(db, "bitrix_webhook_url", "")
        bitrix_service.webhook_url = ""
    elif payload.webhook_url is not None and payload.webhook_url.strip() != "":
        SettingsService.set_setting(db, "bitrix_webhook_url", payload.webhook_url.strip())
        bitrix_service.webhook_url = payload.webhook_url.strip()

    if payload.mock_mode is not None:
        SettingsService.set_setting(db, "bitrix_mock_mode", "true" if payload.mock_mode else "false")
        bitrix_service.mock_mode = payload.mock_mode

    return {
        "mock_mode": bitrix_service.mock_mode,
        "is_configured": bitrix_service.is_configured(),
        "webhook_url_masked": SettingsService.mask_webhook_url(bitrix_service.webhook_url)
    }


@router.post("/bitrix/test")
async def test_bitrix_connection(
    current_user: User = Depends(require_admin)
):
    """Tests real Bitrix24 REST API connection or mock status (ADMIN only)."""
    if bitrix_service.mock_mode:
        return {
            "ok": True,
            "mode": "mock",
            "message": "Демо-режим: внешние запросы не выполняются",
            "status_code": 200,
            "elapsed_ms": 0,
            "error": None
        }

    if not bitrix_service.webhook_url:
        return {
            "ok": False,
            "mode": "live",
            "status_code": 0,
            "elapsed_ms": 0,
            "error": "URL вебхука не настроен"
        }

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{bitrix_service.webhook_url.rstrip('/')}/app.info")
            elapsed = int((time.time() - start_time) * 1000)
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "mode": "live",
                    "status_code": resp.status_code,
                    "elapsed_ms": elapsed,
                    "error": None
                }
            return {
                "ok": False,
                "mode": "live",
                "status_code": resp.status_code,
                "elapsed_ms": elapsed,
                "error": f"Ошибка Bitrix24: HTTP {resp.status_code}"
            }
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        return {
            "ok": False,
            "mode": "live",
            "status_code": 0,
            "elapsed_ms": elapsed,
            "error": str(e)
        }
