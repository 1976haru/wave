@echo off
setlocal
cd /d "%~dp0"
set "PY_CMD="
py -3.13 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3.13"
if not defined PY_CMD py -3.12 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3.12"
if not defined PY_CMD (
  echo WARNING: Python 3.12 or 3.13 is recommended for GPU and PyAV support.
  set "PY_CMD=py -3"
)
%PY_CMD% -c "import sys; print('Using Python', sys.version)"
%PY_CMD% -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe tools\system_check.py
endlocal
