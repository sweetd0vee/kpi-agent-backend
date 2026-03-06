@echo off
REM Переход в корень backend (родитель каталога scripts)
cd /d "%~dp0.."

REM Установка зависимостей тем же Python, которым запускаем скрипт
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo Ошибка установки зависимостей. Проверьте: python -m pip --version
    exit /b 1
)

REM Создание таблиц
python scripts\init_db.py
if errorlevel 1 (
    echo Ошибка создания таблиц. Проверьте DATABASE_URL в .env и доступность PostgreSQL.
    exit /b 1
)
