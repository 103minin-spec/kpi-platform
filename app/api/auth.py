"""
API router for Authentication, user profiles and Demo Switcher.
"""

import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User, UserSession
from app.schemas.schemas import LoginRequest
from app.services.bitrix_service import bitrix_service
from app.services.settings_service import SettingsService
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.get("/users")
def get_users_list(db: Session = Depends(get_db)):
    """Returns all system users for role switching and assignment."""
    users = db.query(User).all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "department_id": u.department_id,
            "department_name": u.department.name if u.department else None,
            "position_id": u.position_id,
            "position_name": u.position.name if u.position else None,
            "bitrix_user_id": u.bitrix_user_id,
            "avatar_url": u.avatar_url
        })
    return out


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Logs in as user by user_id (demo login without password)."""
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    token = secrets.token_urlsafe(32)
    session = UserSession(token=token, user_id=user.id)
    db.add(session)
    db.commit()

    return {
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "department_id": user.department_id,
            "department_name": user.department.name if user.department else None,
            "position_id": user.position_id,
            "position_name": user.position.name if user.position else None,
            "avatar_url": user.avatar_url
        }
    }


@router.post("/logout")
def logout(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db)
):
    """Logs out by invalidating active session."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        db.query(UserSession).filter(UserSession.token == token).delete()
        db.commit()
    return {"status": "ok"}


@router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Returns profile of currently authenticated user."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "department_id": current_user.department_id,
        "department_name": current_user.department.name if current_user.department else None,
        "position_id": current_user.position_id,
        "position_name": current_user.position.name if current_user.position else None,
        "avatar_url": current_user.avatar_url
    }


@router.get("/bitrix/status")
def get_bitrix_status():
    """Returns current Bitrix24 connectivity status."""
    return {
        "mock_mode": bitrix_service.mock_mode,
        "is_configured": bitrix_service.is_configured(),
        "webhook_url": bitrix_service.webhook_url if not bitrix_service.mock_mode else "(Демо-режим активен)"
    }


@router.post("/bitrix/toggle-mock")
def toggle_mock_mode(
    enabled: bool = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Toggles between Mock Mode and live Bitrix24 webhook (ADMIN only)."""
    bitrix_service.mock_mode = enabled
    SettingsService.set_setting(db, "bitrix_mock_mode", "true" if enabled else "false")
    return {"mock_mode": bitrix_service.mock_mode}
