# Music Wave Studio v0.5.2

Interactive audio-reactive waveform designer with cached analysis, live preview, reference-assisted design, true-RGBA CPU/GPU rendering, reusable templates, and batch export.

## Recommended Python Version

Use **Python 3.12 or 3.13 (64-bit)** on Windows. These versions currently provide the best PyAV and ModernGL wheel support. Python 3.14 remains usable in CPU mode with FFmpeg decoding; `install.bat` warns and automatically falls back when the recommended versions are unavailable.

## Install and run

```bat
install.bat
run.bat
```

Use **System Check** in the GUI or run:

```powershell
python tools/system_check.py
```

## Design workflow

1. Add audio and Analyze.
2. Edit the 24fps live preview while audio is playing.
3. Add up to five reference images. Use **Draw ROI** to drag over the waveform, or **Coordinate ROI** for exact numeric input.
4. Review the extracted result before applying it to the current template.
5. Select a gallery preset or save the design to My Templates.
6. Export MP4/H.264, transparent WebM/VP9, or transparent MOV/ProRes 4444.

## Validation and benchmarks

```powershell
python -m pytest -q
python tools/validate_audio.py "D:\MUSIC_FOLDER"
python tools/validate_audio.py "D:\MUSIC_FOLDER" --all
python tools/validate_preview.py
python tools/benchmark_render.py --frames 30
python tools/export_smoke.py
python tools/create_capcut_test.py --seconds 6
```

Reports and CapCut samples are written under `validation_results/` and are intentionally ignored by Git. The CapCut generator creates `01_screen.mp4`, `02_alpha.webm`, `03_prores4444.mov`, and a manual verification checklist.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for implementation details.
