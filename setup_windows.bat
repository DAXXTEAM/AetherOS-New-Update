@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   AetherOS v3.0 Singularity - Official Setup Wizard
echo ========================================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python from python.org
    pause
    exit /b
)

echo [1/4] Installing all system dependencies...
pip install -r requirements_full.txt

echo.
echo [2/4] Verifying Ollama installation...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama not found. Local offline mode will not work.
    echo Please download from https://ollama.com/ if you want offline AI.
) else (
    echo [OK] Ollama detected. Pulling Llama3 model (this may take time)...
    ollama pull llama3
)

echo.
echo [3/4] Initializing AetherOS Workspace...
if not exist "%USERPROFILE%\aetheros_workspace" mkdir "%USERPROFILE%\aetheros_workspace"
if exist "%USERPROFILE%\.aetheros\.killswitch" del "%USERPROFILE%\.aetheros\.killswitch"

echo.
echo [4/4] Setup Complete!
echo.
echo --------------------------------------------------------
echo   To start the AI Pilot (CLI):  python aetheros.py
echo   To start the Control Panel:   python aetheros.py --gui
echo --------------------------------------------------------
echo.
set /p launch="Do you want to start AetherOS now? (Y/N): "
if /i "%launch%"=="Y" (
    python aetheros.py
)

pause
