# Music Wave Studio v0.7

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

## Audio Analysis v2

The STANDARD analyzer uses NumPy plus SciPy when available. FFT windowing supports Hann (default), Hamming, and Blackman. Spectrum mapping supports LOG and dependency-free PERCEPTUAL (mel-like) bands. Seven internal bands (sub, bass, low-mid, mid, upper-mid, high, air) feed the simple Bass/Mid/High controls. Analysis occurs once and is cached as numeric NPZ plus versioned JSON metadata; render frames never run FFT or SciPy filters.

Librosa is experimental and is not bundled in the Standard executable. Install it only when needed:

```powershell
python -m pip install -r requirements-advanced.txt
python tools/compare_analyzers.py "D:\music\song.wav"
```

## Playlist and automation

The Playlist tab supports files/folders, ordering, per-track preset/format data, save/load as `.mwsplaylist.json`, and retry state. Headless rendering uses the same cache and renderer pipeline:

```powershell
python app.py --headless --job job.json
python app.py --headless --audio "D:\music\song.wav" --preset "Tokyo Night" --output "D:\output" --format webm
```

See [PLAYLIST_STUDIO_HUB_INTEGRATION.md](PLAYLIST_STUDIO_HUB_INTEGRATION.md) for the stable job/result contract. Run the consolidated release check with `python tools/final_validation.py --exports`.

## FFmpeg resolution

Runtime lookup order is a user-selected FFmpeg path, an executable-adjacent bundled path (reserved for future packages), then system `PATH`. The Standard v0.7 build does not bundle FFmpeg. Python 3.12 64-bit is the official build target; 3.13 is supported when all wheels are available, while 3.14 is CPU-fallback only and not recommended.
## v0.8.0 packaged reference workflow and analysis progress

The default GUI language is Korean. The five-step path is audio selection, style, preview, export settings, and run. Advanced controls remain available behind Advanced Settings. Up to five job sets can be saved in queue_state.json, preflight-checked, reordered, resumed after restart, and processed sequentially while individual track/set failures are recorded and skipped. Rendering temporarily prevents Windows sleep when enabled. English is available from the language selector.

## v0.8.0 Built-in preset gallery

42개의 내장 파형 스타일과 카테고리별 thumbnail gallery를 제공합니다. 기본 workflow는 음원 폴더 → 스타일 → 미리보기 → 대기열 → 시작이며, 참고 이미지 분석은 고급 기능으로 유지됩니다.


## v0.8.0 visual renderer upgrade

Ribbon, Ring, Radial geometry와 showcase thumbnail/contact sheet 검증 도구를 포함합니다.


