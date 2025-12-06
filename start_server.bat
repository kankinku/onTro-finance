@echo off
title OntoFin v4.0 Server Launcher
echo ========================================================
echo       Ontology-based Financial Scenario System
echo                  (OntoFin v4.0)
echo ========================================================
echo.

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH! Please install Python 3.10+.
    pause
    exit /b
)

:: 2. Set Project Root to current directory
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"
set "PYTHONPATH=%PROJECT_ROOT%"

echo [INFO] Project Root: %PROJECT_ROOT%
echo.

:: 3. Install Dependencies (fast check)
echo [INFO] Ensuring dependencies are installed...
pip install -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Dependency install failed. Attempting to run anyway...
) else (
    echo [INFO] Dependencies OK.
)
echo.

:: 4. Run Server
echo [INFO] Starting API Server execution...
echo [INFO] Please keep this window open. Access Swagger UI at: http://127.0.0.1:8000/docs
echo.

python src/main.py

:: 5. Pause on exit
echo.
echo [SERVER STOPPED]
pause
