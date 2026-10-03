@echo off
setlocal
cd /d "%~dp0"
set "VERSION=0.8.5.3"
set "TARGET=dist\MusicWaveStudio_v%VERSION%"
if exist "build\music_wave_studio" rmdir /s /q "build\music_wave_studio"
if exist "%TARGET%" rmdir /s /q "%TARGET%"
if exist "dist\MusicWaveStudio_v%VERSION%.exe" del /q "dist\MusicWaveStudio_v%VERSION%.exe"
if exist ".venv312\Scripts\python.exe" (
  set "PY=.venv312\Scripts\python.exe"
) else (
  if not exist ".venv\Scripts\python.exe" call install.bat
  set "PY=.venv\Scripts\python.exe"
)
"%PY%" -m pip install pyinstaller
"%PY%" -m PyInstaller --noconfirm --clean music_wave_studio.spec
if not exist "%TARGET%\MusicWaveStudio_v%VERSION%.exe" exit /b 20
if not exist "%TARGET%\_internal\python312.dll" exit /b 21
if exist "dist\MusicWaveStudio_v%VERSION%.exe" exit /b 22
endlocal
