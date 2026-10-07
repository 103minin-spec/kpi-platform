@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   KPI Formula Engine - запуск платформы
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python не найден в PATH.
  echo     Установите Python 3.11+ с python.org и запустите файл снова.
  echo.
  pause
  exit /b 1
)

echo [1/3] Проверяю зависимости (первый запуск может занять минуту)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo [!] Не удалось установить зависимости. Проверьте интернет и повторите.
  pause
  exit /b 1
)

echo [2/3] Запускаю сервер в отдельном окне...
start "KPI Platform (сервер)" cmd /k "chcp 65001 >nul & python run.py"

echo [3/3] Открываю браузер...
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:8000

echo.
echo Готово. Адрес платформы:  http://127.0.0.1:8000
echo Документация API:        http://127.0.0.1:8000/docs
echo.
echo Сервер работает в отдельном окне - закройте его, чтобы остановить.
echo.
pause
