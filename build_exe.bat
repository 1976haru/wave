@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name MusicWaveStudio --collect-all moderngl --collect-all av --add-data "templates;templates" app.py
endlocal
