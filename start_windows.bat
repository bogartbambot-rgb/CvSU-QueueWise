@echo off
setlocal
cd /d "%~dp0"
title CvSU QueueWise - Starting local server
where py >nul 2>&1
if %errorlevel% equ 0 (
  set "PYTHON=py -3"
) else (
  set "PYTHON=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating the virtual environment...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto error
)
echo [2/3] Installing required Python packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo [3/3] Starting CvSU QueueWise...
echo Open http://127.0.0.1:8000 in your browser.
echo Press CTRL+C to stop the server.
echo.
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto error
goto end
:error
echo.
echo Setup or launch failed. Check that Python 3.10+ and internet access are available.
pause
:end
endlocal
