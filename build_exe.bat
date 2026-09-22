@echo off
setlocal
cd /d "%~dp0"
if exist ".venv312\Scripts\python.exe" (
  set "PY=.venv312\Scripts\python.exe"
) else (
  if not exist ".venv\Scripts\python.exe" call install.bat
  set "PY=.venv\Scripts\python.exe"
)
"%PY%" -m pip install pyinstaller
"%PY%" -m PyInstaller --noconfirm --clean music_wave_studio.spec
endlocal
