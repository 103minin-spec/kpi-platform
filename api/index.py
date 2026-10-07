"""
Точка входа для serverless-развёртывания на Vercel.

Vercel ищет в файле функцию-обработчик ASGI: переменная называется `app`.
Всё приложение (API + статика) обслуживается одной функцией, поэтому в
`vercel.json` настроен rewrite всех путей на этот файл.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402  (ASGI-приложение для рантайма Vercel)

__all__ = ["app"]
