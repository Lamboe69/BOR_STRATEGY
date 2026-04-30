@echo off
echo ========================================
echo Starting BOR Trading Bot Dashboard
echo ========================================
echo.
echo Dashboard will open at: http://localhost:5000
echo.
echo Press Ctrl+C to stop the dashboard
echo ========================================
echo.

cd /d "%~dp0"
python ui\dashboard.py

pause
