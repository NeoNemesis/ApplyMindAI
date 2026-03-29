@echo off
chcp 65001 > nul
title ApplyMind AI — Webbgränssnitt

echo.
echo ============================================================
echo   ApplyMind AI -- Webbgranssnitt
echo ============================================================
echo   Startar server pa http://localhost:5000
echo   Tryck Ctrl+C for att stoppa
echo ============================================================
echo.

cd /d "%~dp0"
start http://localhost:5000
python web_app.py

pause
