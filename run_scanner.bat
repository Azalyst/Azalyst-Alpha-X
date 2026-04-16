@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

title BB Scanner - Institutional Grade - Binance BB(200,1)
color 0A
cls

echo.
echo ==========================================================
echo   BB SCANNER - INSTITUTIONAL GRADE
echo   Binance Perpetual 5m BB(200,1) 30x Paper Trading
echo   Discord Alerts - Chart Images - Paper Portfolio
echo ==========================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.10+ from https://python.org
    echo Make sure "Add Python to PATH" is enabled during install.
    goto :launcher_error
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYVER=%%i"
echo [OK] %PYVER% detected.
echo.

echo [1/2] Installing / verifying dependencies...
echo       pandas numpy matplotlib requests
echo.

python -m pip install --upgrade --quiet pandas numpy matplotlib requests
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed.
    echo Try running this manually:
    echo   python -m pip install --upgrade pandas numpy matplotlib requests
    goto :launcher_error
)

echo [1/2] Dependencies OK.
echo.

python -c "import matplotlib; print('  [OK] matplotlib', matplotlib.__version__, '- chart images ENABLED')" 2>nul
if errorlevel 1 (
    echo [WARN] matplotlib not importable - Discord alerts will be text only.
    echo        Run: python -m pip install matplotlib
)
echo.

echo [2/2] Starting scanner...
echo.
python -X utf8 bb_scanner.py
set "EXITCODE=%ERRORLEVEL%"

echo.
echo ----------------------------------------------------------
if "%EXITCODE%"=="0" (
    echo Scanner exited cleanly.
) else (
    echo [ERROR] Scanner exited with code %EXITCODE%.
)
echo Press any key to close.
pause >nul
exit /b %EXITCODE%

:launcher_error
echo.
echo Press any key to close.
pause >nul
exit /b 1
