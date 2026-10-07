"""
FastAPI application entrypoint for Employee KPI & Performance Platform.
"""

import os
from dotenv import load_dotenv

load_dotenv()
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import engine, SessionLocal, Base
from app.seed import seed_database
from app.services.demo_service import warmup_demo_data
from app.services.settings_service import SettingsService
from app.api import auth, formulas, departments, periods, export, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema is created
    Base.metadata.create_all(bind=engine)
    # Seed initial company structure & formulas
    db = SessionLocal()
    try:
        seed_database(db)
        SettingsService.init_settings(db)
        # В демо-режиме сразу считаем последний период, чтобы дашборд был не пустым
        await warmup_demo_data(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="KPI & Employee Performance Platform",
    description="Веб-платформа для настройки формул эффективности и расчета премий сотрудников на основе данных Битрикс24",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:8000")
cors_origins = [orig.strip() for orig in cors_origins_env.split(",") if orig.strip()]
allow_credentials = False if "*" in cors_origins else True

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(auth.router)
app.include_router(formulas.router)
app.include_router(departments.router)
app.include_router(periods.router)
app.include_router(export.router)
app.include_router(settings.router)

# Mount Static Assets & Frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "KPI Platform API is running. Static UI not yet created."}
