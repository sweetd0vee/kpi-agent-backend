@echo off
setlocal

set "script_dir=%~dp0"
for %%i in ("%script_dir%..\\..") do set "repo_root=%%~fi"

docker build -t ai-kpi-backend:local -f "%repo_root%\docker\app\Dockerfile" "%repo_root%"

endlocal
