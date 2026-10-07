"""
Authentication and Authorization dependencies.
"""
from fastapi import Header, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User, UserSession


def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация (отсутствует заголовок Authorization: Bearer <token>)"
        )
    token = authorization.split("Bearer ", 1)[1].strip()
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session or not session.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истекший токен сессии"
        )
    return session.user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен: действие доступно только администратору"
        )
    return current_user


def require_head_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("ADMIN", "HEAD"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен: действие доступно только руководителю или администратору"
        )
    return current_user
