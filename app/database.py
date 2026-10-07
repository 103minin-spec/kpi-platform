"""
Database setup for KPI Platform (SQLite by default, PostgreSQL ready).
"""

import os
import sqlite3
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

def _default_database_url() -> str:
    """На serverless-хостинге (Vercel) файловая система только для чтения, кроме /tmp."""
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/kpi.db"
    return "sqlite:///./kpi.db"


DATABASE_URL = os.getenv("DATABASE_URL") or _default_database_url()

# SQLite needs connect_args check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

