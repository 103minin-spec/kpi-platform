"""
Starter script for Employee KPI & Performance Platform.
Starts FastAPI server on http://localhost:8000
"""

import sys
import os

# Fix Windows console encoding for Unicode/UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

import uvicorn

if __name__ == "__main__":
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    if curr_dir not in sys.path:
        sys.path.insert(0, curr_dir)

    print("=" * 70)
    print("KPI & Employee Performance Platform (Bitrix24 Formula Engine)")
    print("=" * 70)
    print("Локальный адрес платформы:   http://localhost:8000")
    print("Документация Swagger API:     http://localhost:8000/docs")
    print("Демо-режим активирован по умолчанию (Mock Data)")
    print("=" * 70)

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
