@echo off
setlocal

set COMPOSE_PROJECT_NAME=ai-kpi
docker-compose -f "%~dp0docker-compose.yml" --env-file "%~dp0.env" down

endlocal
