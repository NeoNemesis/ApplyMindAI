@echo off
chcp 65001 > nul
title ApplyMind AI -- Installera genvag

echo.
echo ============================================================
echo   ApplyMind AI -- Skapar skrivbordsgenväg
echo ============================================================
echo.

cd /d "%~dp0"

:: Find pythonw.exe
for /f "tokens=*" %%i in ('python -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))" 2^>nul') do set PYTHONW=%%i

if not exist "%PYTHONW%" (
    set PYTHONW=%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe
)

if not exist "%PYTHONW%" (
    echo FEL: pythonw.exe hittades inte.
    echo Se till att Python ar installerat korrekt.
    pause
    exit /b 1
)

echo Python: %PYTHONW%
echo App: %~dp0ApplyMindAI.pyw
echo.

:: Create shortcut via PowerShell
:: Get correct desktop path (works with OneDrive-redirected desktops)
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set DESKTOP=%%i
set SHORTCUT=%DESKTOP%\ApplyMind AI.lnk
set ICON=%~dp0assets\app_icon.ico
set TARGET=%PYTHONW%
set ARGS="%~dp0ApplyMindAI.pyw"
set WORKDIR=%~dp0

:: Remove old shortcut if it exists
if exist "%DESKTOP%\JobCraftAI.lnk" del "%DESKTOP%\JobCraftAI.lnk"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%SHORTCUT%'); ^
   $s.TargetPath = '%TARGET%'; ^
   $s.Arguments = '%ARGS%'; ^
   $s.WorkingDirectory = '%WORKDIR%'; ^
   $s.IconLocation = '%ICON%'; ^
   $s.Description = 'ApplyMind AI - AI-drivet jobbsoekningssystem'; ^
   $s.WindowStyle = 1; ^
   $s.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo ============================================================
    echo   Klart! Genvaeg skapad pa skrivbordet.
    echo   Dubbelklicka "ApplyMind AI" pa skrivbordet for att starta.
    echo ============================================================
) else (
    echo FEL: Genvaegen kunde inte skapas.
    echo Prova att kora som administratör.
)

echo.
pause
