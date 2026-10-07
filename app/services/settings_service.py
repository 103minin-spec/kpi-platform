"""
Service for managing application settings stored in the database.
"""

from typing import Optional
from sqlalchemy.orm import Session
from app.models.entities import AppSetting
from app.services.bitrix_service import bitrix_service


class SettingsService:
    @staticmethod
    def get_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        return setting.value if setting and setting.value is not None else default

    @staticmethod
    def set_setting(db: Session, key: str, value: Optional[str]) -> None:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not setting:
            setting = AppSetting(key=key, value=value)
            db.add(setting)
        else:
            setting.value = value
        db.commit()

    @staticmethod
    def init_settings(db: Session) -> None:
        """Loads settings on startup and configures bitrix_service singleton."""
        wh_url = SettingsService.get_setting(db, "bitrix_webhook_url")
        if wh_url:
            bitrix_service.webhook_url = wh_url

        mock = SettingsService.get_setting(db, "bitrix_mock_mode")
        if mock is not None:
            bitrix_service.mock_mode = mock.lower() in ("true", "1", "yes")

    @staticmethod
    def mask_webhook_url(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        clean = url.rstrip("/")
        parts = clean.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:-1]) + "/****"
        return "https://****"
