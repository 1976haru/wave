# Music Wave Studio v0.6

Production-oriented audio-reactive waveform designer with cached analysis, responsive live preview, reference-assisted design, CPU/GPU RGBA rendering, resumable batch export, reusable templates, and Windows distribution support.

## Recommended environment

- Windows 10/11 64-bit
- Python 3.12 64-bit (primary development and distribution target)
- Python 3.13 64-bit is also supported
- FFmpeg and ffprobe available on `PATH`

Python 3.14 can run in CPU/FFmpeg fallback mode, but current ModernGL/PyAV wheel availability may vary. `install.bat` selects Python 3.13 or 3.12 and runs the system check.

## Install and run

```bat
install.bat
run.bat
```

Run readiness checks with:

```powershell
python tools/system_check.py
```

## Preview and rendering

Preview rendering runs in a dedicated QThread. The GUI submits to a single-slot mailbox, so a new request replaces any stale pending frame. Audio time remains authoritative and late frames are dropped instead of queued.

Quality profiles:

- `PREVIEW`: 24fps analysis, 1/4-resolution glow, CRF 28, veryfast encoding.
- `BALANCED`: 30fps, 1/2-resolution glow, CRF 20, general YouTube/CapCut use.
- `QUALITY`: 30fps, full-resolution glow, CRF 17, slow encoding.

Quality profiles never change the requested output resolution.

## Batch resume

Every batch writes `batch_state.json` atomically. Tracks transition through pending, rendering, completed, failed, or cancelled. Enable **Skip completed outputs** to resume without rebuilding valid completed files. `error_report.json` remains available for failures.

## Validation and profiling

```powershell
python -m pytest -q
python tools/validate_audio.py "D:\MUSIC_FOLDER"
python tools/validate_audio.py "D:\MUSIC_FOLDER" --all
python tools/validate_preview.py
python tools/profile_render.py --frames 60
python tools/benchmark_render.py --frames 30
python tools/export_smoke.py
python tools/create_capcut_test.py --seconds 6
```

Validation output is written under `validation_results/` and excluded from Git. Real user music is never committed.

## Windows executable

```bat
build_exe.bat
```

The application is created at `dist\MusicWaveStudio\MusicWaveStudio.exe`. Templates and required Python/Qt/PyAV/ModernGL resources are bundled. **FFmpeg is not bundled**; the executable uses `ffmpeg.exe` and `ffprobe.exe` from the system `PATH`. The GUI System Check reports missing codecs or tools.

## CapCut package

`tools/create_capcut_test.py` creates MP4 Screen-blend, VP9-alpha WebM, ProRes 4444 MOV, and `CAPCUT_TEST_CHECKLIST.txt`. Generation does not mean CapCut compatibility has passed; a user must complete the checklist in the actual CapCut version.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for implementation details.
