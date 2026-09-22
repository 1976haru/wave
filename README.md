# Music Wave Studio v0.5.1

Interactive audio-reactive waveform designer built as four independent layers: cached audio analysis, frequency-aware animation, CPU/GPU RGBA rendering, and reusable JSON templates.

## Run on Windows

```bat
install.bat
run.bat
```

Python 3.10–3.13 is recommended for PyAV and ModernGL. Python 3.14 automatically uses the FFmpeg decoder and CPU renderer because upstream wheels are not yet available.

## Workflow

1. Add audio and click **Analyze**.
2. Play the 24 fps cached preview while editing Audio, Design, and Effects controls.
3. Add up to five reference images or a 5–10 second video, optionally define an ROI, and apply analyzed style/motion values.
4. Select one of eight gallery templates or save the current design under **My Templates**.
5. Export H.264 MP4, transparent VP9 WebM, or transparent ProRes 4444 MOV.

## Validation

```powershell
python -m pytest -q
python tools/validate_audio.py "D:\music"
```

Folder validation writes `validation_results/report.json`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for internals.
