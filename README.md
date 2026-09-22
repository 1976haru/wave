# Music Wave Studio v0.5

Music Wave Studio turns audio features into customizable animated waveform videos. It uses four independent layers: audio analysis, animation, design rendering, and JSON templates.

## Quick start (Windows)

Run `install.bat`, then `run.bat`. FFmpeg on `PATH` is recommended for decoder fallback and export. ModernGL is optional: `AUTO` uses the GPU when available and otherwise uses the CPU.

```powershell
python -m pip install -r requirements.txt
python app.py
python -m pytest -q
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.
