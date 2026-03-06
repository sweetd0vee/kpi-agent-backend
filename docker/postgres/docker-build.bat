@echo off
REM Переход в корень backend (где лежит папка docker), независимо от текущей директории
cd /d "%~dp0..\.."

docker build -t sber/ai-kpi/postgres:16.9-bookworm -f docker/postgres/Dockerfile .