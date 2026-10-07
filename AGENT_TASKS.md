# AGENT_TASKS.md — план исправлений KPI Platform

> Этот файл — задание для автономного агента-разработчика. Читай его целиком, затем выполняй задачи по порядку приоритета.

## 0. Контекст проекта

- Стек: Python 3.13, FastAPI, SQLAlchemy 2.0 (SQLite `kpi.db`), Pydantic v2, openpyxl, pytest (+ anyio).
- Фронтенд: два файла — `app/static/index.html` и `app/static/app.js` (Vue 3 + Tailwind + Lucide + Chart.js, всё с CDN, сборки нет).
- Структура: `app/main.py` (точка входа), `app/api/*` (роутеры), `app/services/*` (логика), `app/models/entities.py` (ORM), `app/schemas/schemas.py` (Pydantic), `app/seed.py` (демо-данные), `tests/`.
- Запуск: `python run.py` → http://localhost:8000, Swagger — `/docs`.
- Тесты: `python -m pytest tests/ -v` (сейчас **7 passed**).
- Сквозная проверка: запустить сервер и выполнить `python verify_e2e.py`.

Состояние: приложение работает, тесты зелёные, но есть подтверждённые дефекты (ниже). Дефекты воспроизводимы, каждый описан с текущим и требуемым поведением.

## 1. Правила работы

1. Перед правкой читай файл целиком; правки — точечные, без переписывания архитектуры.
2. Пользовательские тексты, сообщения об ошибках и подписи в UI — **на русском**.
3. Не удаляй и не переименовывай существующие рабочие URL, кроме случаев, прямо указанных в задаче.
4. **После каждой задачи** запускай `python -m pytest tests/ -v`; набор тестов должен оставаться зелёным.
5. На каждый исправленный дефект добавляй **регрессионный тест**. Задача без теста не считается выполненной.
6. Тесты не должны трогать рабочий `kpi.db`: используй `sqlite:///:memory:` или временный файл и `app.dependency_overrides[get_db]`.
7. Если меняешь схему БД — удали `kpi.db` перед следующим запуском (демо-данные пересеются автоматически в `lifespan`).
8. Не добавляй новых зависимостей без необходимости; если добавил — обнови `requirements.txt`.
9. Не коммить `kpi.db`, `__pycache__`, `.pytest_cache` (см. задачу T9).
10. В конце отчёта по каждой задаче указывай: файлы, суть изменения, добавленные тесты, вывод pytest.

## 2. Задачи

### T1 (P0). Формула с несуществующей переменной сохраняется и молча обнуляет премии

**Файлы:** `app/services/formula_engine.py`, `app/api/formulas.py`, `tests/test_formula_validation.py` (новый).

**Сейчас.** `FormulaEngine.test_sandbox()` ([formula_engine.py](app/services/formula_engine.py:216)) подставляет любому неизвестному имени значение `100.0`, поэтому формула с опечаткой проходит проверку:

```
PUT /api/formulas/templates/1  {"formula_expression": "IF(deals_won_sum_typo >= plan_sales, base_rate * 0.7, base_rate * 0.1)"}
→ 200 OK, "Синтаксис корректен"
```

При расчёте периода переменной нет в контексте → `NameError` → `except FormulaError` в `CalculationService` → премия `0.0`:
`notes = "Ошибка формулы: ... name 'deals_won_sum_typo' is not defined"`.

**Надо.**
1. В `FormulaEngine` добавь строгую проверку имён: множество допустимых имён = `{item["name"] for item in CATALOG}`. Все имена из формулы, которых нет в этом множестве, — ошибка.
2. Введи метод `FormulaEngine.validate(expr: str) -> None` (или флаг `strict=True` в `test_sandbox`), который поднимает `FormulaError` с текстом вида:
   `Неизвестные переменные: deals_won_sum_typo. Допустимые: deals_won_sum, deals_won_count, ...`
3. `test_sandbox()` в строгом режиме возвращает `{"valid": False, "error": ..., "unknown_vars": [...]}`.
4. В `PUT /api/formulas/templates/{position_id}` ([formulas.py](app/api/formulas.py:65)) — при `valid=False` возвращать `400` с текстом ошибки (сейчас уже возвращает 400, но только на синтаксис — должно ловить и неизвестные имена).
5. `POST /api/formulas/sandbox/test` — в ответ добавь поле `unknown_vars` (список), фронтенд его покажет (см. T11).

**Проверка (обязательный тест).**
- `PUT` с опечаткой → `400`, в `detail` упомянуто неизвестное имя.
- `PUT` с валидной формулой → `200`.
- `sandbox/test` для формулы с опечаткой → `valid == False`, `unknown_vars == ["deals_won_sum_typo"]`.
- Регресс: все формулы из `app/seed.py` проходят `validate()` без ошибок.

---

### T2 (P0). «KPI, %» не связан с формулой премии и показывает 100 % при нулевой выручке

**Файлы:** `app/services/calculation_service.py`, `tests/test_calculation.py`.

**Сейчас.** [calculation_service.py](app/services/calculation_service.py:96):

```python
if plan_sales > 0 and actual_metrics.get("deals_won_sum", 0) > 0:
    kpi_pct = round((actual_metrics.get("deals_won_sum", 0) / plan_sales) * 100, 1)
elif plan_tasks > 0 and actual_metrics.get("tasks_closed", 0) > 0:
    kpi_pct = round((actual_metrics.get("tasks_closed", 0) / plan_tasks) * 100, 1)
else:
    kpi_pct = 100.0
```

Проверено на живом расчёте: при **нулевой выручке** все 5 сотрудников получают `kpi_percent = 100.0`, дашборд показывает «Норматив выполнен» и «Выполнили план: 5 из 5».

**Надо.**

```python
fact_sales = float(actual_metrics.get("deals_won_sum", 0.0) or 0.0)
fact_tasks = float(actual_metrics.get("tasks_closed", 0.0) or 0.0)

if plan_sales > 0:
    kpi_pct = round(fact_sales / plan_sales * 100, 1)
elif plan_tasks > 0:
    kpi_pct = round(fact_tasks / plan_tasks * 100, 1)
else:
    kpi_pct = 0.0
```

Условия `> 0` у факта убрать: нулевой факт — это 0 %, а не «нет данных». Ветки `else: 100.0` быть не должно. Перевыполнение (`> 100 %`) не обрезать.

**Проверка (обязательный тест).** `tests/test_calculation.py::test_kpi_percent_is_zero_without_facts`: подменить `bitrix_service.get_employee_metrics` на функцию, возвращающую нулевые метрики, рассчитать период и убедиться, что `kpi_percent == 0.0` у сотрудников с `plan_sales > 0`, и что ни одна строка не имеет `kpi_percent == 100.0`.

> Примечание (не обязательно в этой задаче): KPI % по-прежнему считается отдельной эвристикой, а не из формулы премии. Если нужно полное соответствие — добавь в `EmployeeTarget` поле `kpi_metric` (`SALES` / `TASKS` / `CALLS`, default `SALES`), заполни его в `seed.py` по ролям и считай KPI по выбранному показателю. Тогда обязательно удали `kpi.db` и обнови `TargetUpdate` и экран «Индивидуальные планы».

---

### T3 (P0). Аутентификации нет, роли задаются клиентом в query-параметрах

**Файлы:** `app/api/deps.py` (новый), `app/api/auth.py`, `app/api/periods.py`, `app/api/formulas.py`, `app/api/companies*` (`departments.py`), `app/api/export.py`, `app/models/entities.py`, `app/static/app.js`, `tests/test_auth.py` (новый).

**Сейчас.** Проверено запросами:

```
GET /api/periods/3/results                              → 5 строк (ФИО, оклады, премии всех сотрудников)
GET /api/periods/3/results?role=EMPLOYEE&user_id=3      → 1 строка
GET /api/periods/3/results?role=ADMIN&user_id=3         → 5 строк   # сотрудник «поднял» себе роль
```

`role` и `user_id` — обычные query-параметры ([periods.py](app/api/periods.py:86)); паролей/токенов/сессий нет вообще. Фронтенд вообще не передаёт эти параметры ([app.js](app/static/app.js:167)), то есть любой сотрудник видит оклады и премии коллег. В `README.md` заявлен «ролевой доступ» — это надо привести в соответствие.

**Надо (минимальный рабочий вариант, без внешних библиотек).**
1. Модель `UserSession`: `id`, `token` (уникальный), `user_id` (FK), `created_at`. Токен — `secrets.token_urlsafe(32)`.
2. `POST /api/auth/login` с телом `{"user_id": int}` → `{"token": ..., "user": {...}}`; `POST /api/auth/logout` (удаляет сессию). Демо-вход без пароля допустим, но это должно быть явно написано в README («демо-вход без пароля, только для показа»).
3. `app/api/deps.py`: `get_current_user(authorization: str | None = Header(None), db = Depends(get_db))` — читает `Authorization: Bearer <token>`, ищет сессию, возвращает `User`, иначе `HTTPException(401)`.
4. Удали из `GET /api/periods/{id}/results` параметры `role` и `user_id`; фильтрация — по роли из БД: `ADMIN` — все, `HEAD` — только свой `department_id`, `EMPLOYEE` — только себя.
5. Права на изменение: формулы (`PUT /api/formulas/templates/{id}`), расчёт и фиксация периода, `PUT .../targets/{user_id}`, переключение mock-режима — только `ADMIN`; `HEAD` — планы только своего отдела. Иначе `403`.
6. `GET /api/company/structure`, `/employees`, `/periods/{id}/targets` — только `ADMIN`/`HEAD` (EMPLOYEE — `403`).
7. Фронтенд: экран/селект пользователя вызывает `/api/auth/login`, токен хранится в `localStorage`, все `fetch` добавляют заголовок `Authorization: Bearer <token>`. Ссылки экспорта (`window.location.href`) заменить на `fetch` + `Blob` + `URL.createObjectURL`, иначе заголовок не передаётся. При `401` — сбросить токен и показать экран входа.

**Проверка (обязательные тесты).** Без заголовка → `401`. С токеном сотрудника `/api/periods/{id}/results` → ровно 1 строка (своя). С токеном руководителя — только сотрудники его отдела. Запрос с `?role=ADMIN` от сотрудника → результат не меняется. `PUT` формулы сотрудником → `403`.

---

### T4 (P0). Кнопка «Вкл. Live / Вкл. Mock» уходит в 404

**Файлы:** `app/static/app.js`, `tests/test_api_routes.py` (новый).

**Сейчас.** Фронт вызывает несуществующий маршрут ([app.js](app/static/app.js:191)):

```
POST /api/auth/toggle-mock         → 404 {"detail":"Not Found"}
POST /api/auth/bitrix/toggle-mock  → 200 {"mock_mode": false}   # реальный маршрут, auth.py:69
```

Из-за этого `bitrixStatus.value.mock_mode = (await resp.json()).mock_mode` получает `undefined`, и UI самопроизвольно показывает «Битрикс24 Live», ничего не переключая.

**Надо.** Исправить URL в `app.js` на `/api/auth/bitrix/toggle-mock`; проверять `resp.ok` и показывать ошибку (как это сделано в `triggerCalculation`), не подменять состояние при неуспехе. Доступ к эндпоинту — только `ADMIN` (см. T3).

**Проверка.** Тест: маршрут присутствует в `app.openapi()["paths"]`, `POST` от администратора → `200` и `mock_mode` меняется; от сотрудника → `403`. Ручная проверка: кнопка переключает индикатор и после `F5` состояние сохраняется.

---

### T5 (P1). Вкладка «Интеграция Битрикс24» — декорация

**Файлы:** `app/static/app.js`, `app/api/settings.py` (новый), `app/services/settings_service.py` (новый), `app/models/entities.py`, `app/main.py`.

**Сейчас.** `testBitrixConnection` ([app.js](app/static/app.js:370)) просто показывает «Соединение успешно проверено», не выполняя запросов. Поле `bitrixWebhookInput` никуда не отправляется: в `openapi.json` **нет ни одного** эндпоинта для вебхука (проверено — 19 путей).

**Надо.**
1. Таблица `AppSetting(key, value)` и сервис чтения/записи.
2. `GET /api/settings/bitrix` → `{"mock_mode": bool, "is_configured": bool, "webhook_url_masked": "https://portal.bitrix24.ru/rest/1/****"}`. Полный URL в ответе не отдавать.
3. `PUT /api/settings/bitrix` `{"webhook_url": str | null, "mock_mode": bool | null}` — валидировать, что URL начинается с `https://` и содержит `/rest/` (иначе `422`), сохранять в `AppSetting` и применять к singleton `bitrix_service` (при старте — читать из БД).
4. `POST /api/settings/bitrix/test` — **реальная** проверка: в mock-режиме вернуть `{"ok": true, "mode": "mock", "message": "Демо-режим: внешние запросы не выполняются"}`; иначе выполнить `httpx`-запрос к вебхуку (например, `profile` или `app.info`) с таймаутом 10 с и вернуть `{"ok": bool, "status_code": int, "elapsed_ms": int, "error": str | null}`.
5. Фронтенд: `testBitrixConnection` — асинхронный вызов этого эндпоинта с показом реального результата/ошибки; кнопка «Сохранить» вызывает `PUT`; при загрузке вкладки поле заполняется из `GET`.

**Проверка.** Тесты: `PUT` с невалидным URL → `422`; валидный URL сохраняется и возвращается маскированным; `POST .../test` в mock-режиме → `ok=true`; при `BITRIX_MOCK_MODE=false` и недоступном URL → `ok=false` с текстом ошибки (замокать `httpx`). Ручная проверка: введённый URL переживает перезапуск сервера.

---

### T6 (P1). Движок формул: деление на ноль, строковые константы, мёртвый код, префикс `@`

**Файлы:** `app/services/formula_engine.py`, `app/services/calculation_service.py`, `app/static/index.html`, `tests/test_formula_engine.py`.

**Сейчас (проверено вживую).**
- `evaluate("1 / 0")` → `0.0` молча: деление на ноль неотличимо от законного нуля ([formula_engine.py](app/services/formula_engine.py:183)).
- `isinstance(res, (int, float))` стоит раньше `isinstance(res, bool)` ([formula_engine.py](app/services/formula_engine.py:178)) — ветка для `bool` недостижима (`bool` — подкласс `int`).
- `ast.Constant` разрешён любого типа, поэтому `'x' * 20000000` выделяет 20 МБ строки за 0.06 с; `'x' * 10**10` — потенциальный отказ в обслуживании (эндпоинт песочницы не требует авторизации). Длины формулы не ограничены.
- UI подсказывает вводить `@deals_won_sum` ([index.html](app/static/index.html:428)), но `evaluate("@deals_won_sum")` → `FormulaError: invalid syntax`, хотя в README ([README.md](README.md:12)) заявлена автоподстановка `@`-переменных.

**Надо.**
1. `ZeroDivisionError` → `FormulaError("Деление на ноль в формуле")` (не `0.0`). В `CalculationService` при `FormulaError` дополнительно писать причину в `notes` и ставить `CalculationResult.status = "ERROR"` (значение премии при этом остаётся `0.0`, но это видно в ведомости и в API).
2. В `validate_ast` запретить строковые/bytes-константы: `ast.Constant` допустим только с `int`, `float`, `bool`.
3. Ограничить длину формулы (например, 4000 символов) — `FormulaError` при превышении.
4. Переставить проверку `bool` перед `(int, float)`.
5. В `preprocess` снимать префикс `@` у имён переменных: `@deals_won_sum` → `deals_won_sum` (регуляркой `@(?=[A-Za-z_])`). Тогда подсказки и README становятся правдой, а `verify_e2e.py` продолжает работать.

**Проверка (тесты).** `1/0` → `FormulaError`; `'abc'` в формуле → `FormulaError`; формула длиной 5000 символов → `FormulaError`; `evaluate("@base_rate")` == `evaluate("base_rate")` при том же контексте; прежние 6 тестов движка остаются зелёными.

---

### T7 (P1). Внешние ключи SQLite не работают, нет проверок существования сущностей

**Файлы:** `app/database.py`, `app/api/departments.py`, `tests/test_database.py` (новый).

**Сейчас.** Проверено: `PRAGMA foreign_keys = 0`. Значит, все `ondelete="CASCADE"` / `"SET NULL"` в `app/models/entities.py` (строки 36, 49, 66–67, 96–97, 126–128) не действуют, а `PUT /api/company/periods/{period_id}/targets/{user_id}` ([departments.py](app/api/departments.py:109)) не проверяет существование периода и пользователя — создаётся «сирота».

**Надо.**
1. В `app/database.py` включить внешние ключи для SQLite через `event.listens_for(engine, "connect")` → `cursor.execute("PRAGMA foreign_keys=ON")`.
2. В `update_employee_target` проверить `Period` и `User` и вернуть `404` с понятным текстом.
3. Аналогичные проверки — в `POST /api/periods/{id}/calculate` и `/lock` (сейчас `ValueError` → `400`, для отсутствующего периода уместнее `404`; сохрани обратную совместимость с `tests/test_calculation.py`, где ожидается текст «заблокирован»).

**Проверка.** Тест: `PRAGMA foreign_keys` == 1; удаление `Department` удаляет его `Position`; `PUT targets` на несуществующий период → `404`.

---

### T8 (P1). Клиент Битрикс24: нет пагинации, не проверяются ошибки, часть метрик выдумана

**Файлы:** `app/services/bitrix_service.py`, `tests/test_bitrix_service.py` (новый).

**Сейчас.** [bitrix_service.py](app/services/bitrix_service.py:49):
- ответы читаются одним запросом, без `start`/`next` (Bitrix24 отдаёт не более 50 записей на страницу) → суммы по сделкам и счётчики задач занижены;
- не проверяется `{"error": ..., "error_description": ...}` в теле ответа — ошибка авторизации выглядит как «нет данных»;
- `calls_count` и `calls_duration_minutes` захардкожены (`100.0` / `250.0`) даже в live-режиме;
- фильтры по датам передаются как `YYYY-MM-DD` без времени.

**Надо.**
1. Реализовать постраничный обход (цикл по `start`, пока в ответе есть `next`) с предохранителем (например, максимум 50 страниц).
2. Проверять `error` / `error_description` и поднимать исключение с текстом ошибки; в `get_employee_metrics` — логировать и уходить в mock-режим (как сейчас), но с явным предупреждением в ответе.
3. Данные телефонии: либо получать реально (`voximplant.statistic.get`), либо **не выдумывать**: если источника нет, возвращать `None` и явно писать в `raw_metrics` пометку, что показатель недоступен (формулы, использующие `calls_count`, должны получать `0`, а не фальшивые 100 звонков).
4. Даты передавать с временем: `f"{start_date}T00:00:00"` / `f"{end_date}T23:59:59"`.

**Проверка (тесты с замоканным `httpx`).** Ответ из двух страниц суммируется корректно; ответ с `{"error": "..."}` → исключение/предупреждение; поля звонков не содержат констант-заглушек.

---

### T9 (P1). Инфраструктура репозитория

**Файлы:** `.gitignore` (новый), `README.md`, `requirements.txt`, `.github/workflows/ci.yml` (новый).

**Сейчас (проверено).** Нет `.git`, `.gitignore`, `Dockerfile`, `LICENSE`, `pyproject.toml`, `.env.example`, `conftest.py`, миграций и CI. В папке лежат артефакты: `kpi.db`, 16 файлов `__pycache__`, `.pytest_cache`. Версии в `requirements.txt` — только нижние границы.

**Надо.**
1. `.gitignore`: `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.db`, `.env`, `.venv/`, `.idea/`, `.vscode/`.
2. Удалить из рабочей папки `kpi.db`, `__pycache__`, `.pytest_cache` (БД создаётся автоматически при первом запуске).
3. `git init` + осмысленный первый коммит.
4. `requirements.txt`: зафиксировать проверенные версии (`fastapi==0.115.*` и т. п. — возьми фактические из окружения и укажи `>=` с указанием мажорной границы).
5. `README.md`: добавить раздел «Известные ограничения» (демо-вход без пароля, SQLite, mock-данные при недоступном Битриксе) и раздел «Архитектура» (слои, где движок формул, где расчёт). Привести в соответствие утверждения: после T3 «ролевой доступ» станет правдой, до этого формулировку надо смягчить.
6. CI (GitHub Actions): `python -m pytest tests/ -v` на push/PR, Python 3.13.

**Проверка.** `git status` чистый после коммита; `python -m pytest tests/ -v` зелёный в чистом клоне; в репозитории нет `*.db` и `__pycache__`.

---

### T10 (P2). CORS и валидация входных данных

**Файлы:** `app/main.py`, `app/schemas/schemas.py`, `app/api/export.py`.

**Сейчас.** `allow_origins=["*"]` вместе с `allow_credentials=True` ([main.py](app/main.py:38)) — несовместимая комбинация. `PeriodCreate` принимает любые строки дат: `"01.12.2026"` пройдёт и уйдёт в фильтр Битрикса. В `export.py` ([export.py](app/api/export.py:81)) `period.name.encode("utf-8")` упадёт при `name is None`.

**Надо.**
1. CORS: список origins из переменной окружения `CORS_ORIGINS` (по умолчанию `http://localhost:8000`), `allow_credentials=False` при `*`.
2. `PeriodCreate`: валидатор формата `YYYY-MM-DD` для `start_date`/`end_date` и проверка `start_date <= end_date` (иначе `422`).
3. `TargetUpdate`: неотрицательные значения, `quality_score` в диапазоне 1–100.
4. Убрать прямое обращение к `period.name` без проверки на `None` (использовать `period.name or f"period_{period_id}"`).

**Проверка.** Тесты: период с `start_date="01.12.2026"` → `422`; `start_date > end_date` → `422`; отрицательный `base_rate` → `422`.

---

### T11 (P2). Устойчивость расчёта периода

**Файлы:** `app/services/calculation_service.py`, `app/api/periods.py`.

**Сейчас.** При исключении внутри цикла нет `rollback()`; `period.status = "CALCULATED"` выставляется даже если сотрудников не рассчитано ни одного; при отсутствии индивидуального плана молча берутся дефолты `50000 / 300000 / 20 / 100 / 100`.

**Надо.**
1. Обернуть тело расчёта в `try/except` с `db.rollback()` и повторным `raise`.
2. Если `results_created == 0` — не менять статус и вернуть `{"employees_calculated": 0, "warnings": [...]}`.
3. Собирать `warnings` для сотрудников без плана: `"У сотрудника <ФИО> нет индивидуального плана на период — использованы значения по умолчанию"`; возвращать их в ответе эндпоинта и показывать в UI (хотя бы `console.warn`/`alert`).
4. Для каждого результата при `FormulaError` писать `notes` с причиной и `status="ERROR"` (см. T6).

**Проверка.** Тест: период без планов возвращает `warnings` непустым; расчёт зафиксированного периода → `400`, статус периода не изменился; ошибка формулы не приводит к частично записанным данным без пометки.

---

### T12 (P2). Фронтенд: мелочи UX

**Файлы:** `app/static/app.js`, `app/static/index.html`.

**Надо.**
1. `insertToken` вставляет токен в позицию курсора, а не в конец строки (сохранять `selectionStart`/`selectionEnd` textarea).
2. После T1 показывать в песочнице список неизвестных переменных из `unknown_vars` (сейчас показывается только общий текст ошибки).
3. Убедиться, что после T3 сотрудник не видит дашборд с чужими выплатами (серверная фильтрация уже вернёт одну строку — проверь, что экран не выглядит пустым/сломанным).
4. Кнопки, доступные только администратору, должны быть скрыты или заблокированы по роли, полученной с сервера (не по локальному состоянию).

**Проверка.** Ручной прогон: вставка переменной в середину формулы работает; сотрудник видит только свою строку; кнопка mock-режима переключается и не «врёт» при ошибке.

---

## 3. Definition of Done

- [ ] `python -m pytest tests/ -v` — все тесты зелёные, число тестов выросло минимум на 10 (по одному на дефект T1–T10).
- [ ] `python run.py` запускается на чистой БД (после удаления `kpi.db`) и демо-данные создаются.
- [ ] `python verify_e2e.py` при запущенном сервере проходит без ошибок (если он ломается из-за новых требований авторизации — обнови скрипт: получи токен через `/api/auth/login` и передавай его в запросах).
- [ ] Ни один ранее работавший сценарий демонстрации из `README.md` не сломан.
- [ ] Отчёт: для каждой задачи — файлы, суть, добавленные тесты, фактический вывод pytest.

## 4-А. Раунд 2 — результаты независимой приёмки (T1–T12 закрыты, остались T13–T17)

Проверено вручную через `TestClient` и живой сервер (`python run.py` + `python verify_e2e.py`): все 10 пунктов сквозного сценария проходят, 44 теста зелёные. Ниже — только то, что **осталось**; задачи T1–T12 выполнены, их переделывать не нужно.

### T13 (P0). Форма настроек Битрикс24 стирает сохранённый вебхук

**Файлы:** `app/static/index.html`, `app/static/app.js`, `app/schemas/schemas.py`, `app/api/settings.py`, `tests/test_settings.py`.

**Сейчас (воспроизведено).**
- `loadBitrixSettings()` ([app.js](app/static/app.js:518)) определена и экспортирована, но **не вызывается нигде**: в `index.html` нет ни одного упоминания. Поэтому при открытии вкладки «Интеграция Битрикс24» поле пустое, а строка «Текущий сохранённый URL» (`bitrixWebhookMasked`) не появляется.
- Кнопка «Сохранить настройки» отправляет `{"webhook_url": ""}`. Валидатор `BitrixSettingsUpdate.validate_webhook_url` ([schemas.py](app/schemas/schemas.py:21)) пустую строку пропускает, `PUT /api/settings/bitrix` возвращает `200` и **очищает** настроенный вебхук.
  Проверено: `PUT {"webhook_url": "https://portal.bitrix24.ru/rest/1/secretkey123/"}` → 200; затем `PUT {"webhook_url": ""}` → 200, `bitrix_service.webhook_url == ""`.
- Второй риск того же места: `mask_webhook_url()` отдаёт `https://portal.bitrix24.ru/rest/1/****`, и эта строка **проходит** валидацию (`https://` + `/rest/`). Если маску подставить в поле ввода и сохранить, в БД уйдёт маска вместо реального URL. Поэтому подставлять маску в `v-model` поля нельзя.

**Надо.**
1. Сохранённый URL показывать только как текст-справку (уже есть `bitrixWebhookMasked`), поле ввода оставить пустым с placeholder.
2. Вызывать `loadBitrixSettings()` при переходе на вкладку: `@click="currentTab = 'settings'; loadBitrixSettings()"` (или watcher по `currentTab`).
3. В `PUT /api/settings/bitrix` трактовать `""` / `None` как «не менять»; либо возвращать `422`. Явную очистку, если нужна, делать отдельным флагом `clear_webhook: true`. Выбери один вариант и покрой тестом.
4. Отклонять (`422`) значение, содержащее маску (`****`), чтобы маску нельзя было сохранить как URL.

**Проверка (тесты).** `PUT {"webhook_url": ""}` не меняет сохранённое значение; `PUT` с маской → `422`; `PUT` валидного URL сохраняется и возвращается замаскированным. Ручной прогон: сохранить URL → перезагрузить страницу → открыть вкладку → видна справка с маской, поле пустое, «Сохранить» ничего не стирает.

---

### T14 (P1). Переключатель mock/live не сохраняется и расходится с вкладкой настроек

**Файлы:** `app/api/auth.py`, `tests/test_api_routes.py`.

**Сейчас (воспроизведено).** `toggle_mock_mode` ([auth.py](app/api/auth.py:107)) меняет только `bitrix_service.mock_mode` в памяти, тогда как `PUT /api/settings/bitrix` пишет значение в `AppSetting`. Проверено: после `POST /api/auth/bitrix/toggle-mock?enabled=false` в БД `bitrix_mock_mode` отсутствует. После перезапуска `SettingsService.init_settings()` вернёт старое значение — то есть кнопка в шапке и вкладка настроек ведут себя по-разному.

**Надо.** Сохранять флаг в БД внутри `toggle_mock_mode` через `SettingsService.set_setting(db, "bitrix_mock_mode", "true"/"false")`, добавив `db: Session = Depends(get_db)`.

**Проверка.** Тест: после `enabled=false` в `AppSetting` лежит `"false"`; повторный `SettingsService.init_settings(db)` не меняет `mock_mode` обратно.

---

### T15 (P2). Эндпоинты, открытые без авторизации

**Файлы:** `app/api/formulas.py`, `README.md`, при необходимости `verify_e2e.py` и тесты.

**Сейчас (проверено).** Без токена отвечают `200`: `/api/auth/users`, `/api/formulas/templates`, `/api/formulas/sandbox/test`, `/api/auth/bitrix/status`.

**Надо.** Закрыть `Depends(get_current_user)` для `GET /api/formulas/templates` и `POST /api/formulas/sandbox/test` (фронтенд уже шлёт токен через `authFetch`). `/api/auth/users` оставить открытым только как демо-список для входа и **явно** описать это в README (раздел «Известные ограничения»): «список пользователей доступен без авторизации — только для демонстрационного стенда». Обновить `verify_e2e.py`/тесты, если они обращаются к закрытым эндпоинтам без токена.

---

### T16 (P2). Мелкие остатки

1. `requirements.txt`: `python-dotenv` не импортируется ни в одном модуле — либо добавить `load_dotenv()` в `run.py`/`app/main.py`, либо убрать зависимость.
2. `app/database.py`: два обработчика `connect` (`engine` и глобальный `Engine`) с одним и тем же `PRAGMA foreign_keys=ON`; глобальный глушит ошибки через `except Exception: pass` и сработает на PostgreSQL. Оставить один (на `engine`) либо проверять диалект.
3. `app/services/bitrix_service.py`: `deals_total_count = max(deals_won_count, 1)`, `conversion_rate` и `tasks_total = tasks_closed + 2` — синтетические значения, выдаваемые за факт. Либо получать реальные данные (отдельный запрос по всем сделкам периода без фильтра стадии), либо пометить как оценочные (`conversion_rate_estimate`) и не использовать в формулах как факт.
4. `README.md`: прямо указать, что `KPI, %` = выполнение плана продаж (а если `plan_sales == 0` — плана задач), и что это **не** процент от формулы премии.

---

### T17 (P0, организационное). Git-репозиторий

**Сейчас.** `git` не установлен в системе (`Get-Command git` пуст), каталога `.git` нет; это единственный невыполненный пункт из T9.

**Надо.** Установить Git, выполнить `git init`, сделать первый коммит, затем коммиты по темам (или один аккуратный коммит с подробным описанием). Убедиться, что в индекс не попали `kpi.db`, `__pycache__`, `.pytest_cache` (они уже в `.gitignore`). Для портфолио это критично: без истории коммитов кейс выглядит как одиночный снимок кода.

---

### Definition of Done раунда 2

- [ ] `python -m pytest tests/ -v` зелёный, добавлены тесты из T13 и T14.
- [ ] `python run.py` + `python verify_e2e.py` — все 10 проверок проходят.
- [ ] Ручной прогон вкладки «Интеграция Битрикс24»: сохранение не стирает URL, маска не подставляется в поле ввода.
- [ ] После перезапуска сервера состояние mock/live совпадает с тем, что показывает интерфейс.
- [ ] `git log` показывает историю проекта.

## 4. Что делать НЕ нужно

- Не переписывать фронтенд на сборщик/фреймворк, не заменять Vue.
- Не менять стек, не добавлять ORM-миграции (Alembic) — достаточно удаления демо-БД.
- Не удалять и не ослаблять существующие тесты.
- Не «глушить» ошибки формул значениями по умолчанию (это и есть причина T1).
- Не добавлять фейковые проверки вида «соединение успешно», если реальный запрос не выполняется.
