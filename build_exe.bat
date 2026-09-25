@echo off
setlocal
cd /d "%~dp0"
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist ".venv312\Scripts\python.exe" (
  set "PY=.venv312\Scripts\python.exe"
) else (
  if not exist ".venv\Scripts\python.exe" call install.bat
  set "PY=.venv\Scripts\python.exe"
)
"%PY%" -m pip install pyinstaller
"%PY%" -m PyInstaller --noconfirm --clean music_wave_studio.spec
set "PKG=dist\MusicWaveStudio_v0.8.3.1"
copy /y "QUICK_START_KR.txt" "%PKG%\QUICK_START_KR.txt" >nul
copy /y "TEST_GUIDE_KR.md" "%PKG%\TEST_GUIDE_KR.md" >nul
copy /y "FEEDBACK_FORM_KR.txt" "%PKG%\FEEDBACK_FORM_KR.txt" >nul
if exist "sample_assets\sample_music_set" xcopy /e /i /y "sample_assets\sample_music_set" "%PKG%\sample_assets\sample_music_set" >nul
if exist "validation_results\v0831_signature_redesign" xcopy /e /i /y "validation_results\v0831_signature_redesign" "%PKG%\validation_results\v0831_signature_redesign" >nul
endlocal
