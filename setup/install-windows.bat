@echo off
rem Setup for Windows. Double-click this file, or run it from a terminal. Safe to run again.
setlocal
cd /d "%~dp0\.."
echo === AI Systematic Review + Wiki: setup ===
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/windows/
  echo During installation, tick "Add python.exe to PATH". Then run this file again.
  goto :fail
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo This template needs Python 3.11 or newer. Install it from https://www.python.org/downloads/windows/
  goto :fail
)

if not exist .venv (
  echo Creating a private Python environment in .venv ...
  %PY% -m venv .venv || goto :fail
)
echo Installing the packages this template needs (a few minutes the first time) ...
.venv\Scripts\python -m pip install --quiet --upgrade pip || goto :fail
.venv\Scripts\python -m pip install --quiet -r setup\requirements.txt || goto :fail

if not exist .env (
  copy .env.example .env >nul
  echo Created .env from .env.example. Add your LibKey or Unpaywall details there later if you have them.
)

echo.
.venv\Scripts\python run.py status
echo.
echo Setup complete. Next: open this folder in your AI assistant (Claude Code or Codex)
echo and ask it to "set up my review". Guides: docs\01-install.md
pause
exit /b 0

:fail
echo.
echo Setup did not finish. See docs\01-install.md, or ask your AI assistant to help with the message above.
pause
exit /b 1
