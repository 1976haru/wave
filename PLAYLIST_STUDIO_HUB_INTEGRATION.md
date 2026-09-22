# Playlist Studio Hub Integration

Music Wave Studio remains an independent process. The stable boundary is job contract version 1.

## Command line

```bat
MusicWaveStudio.exe --headless --job "D:\jobs\wave-job.json"
python app.py --headless --job "D:\jobs\wave-job.json"
python app.py --headless --audio "D:\music\song.wav" --preset "Tokyo Night" --output "D:\output" --format webm
```

## Job JSON

```json
{
  "contract_version": 1,
  "output_dir": "D:/output",
  "preset": "Tokyo Night",
  "format": "webm",
  "export": {"resolution": "1920x1080", "fps": 30, "renderer": "AUTO", "quality": "BALANCED"},
  "tracks": [
    {"audio": "D:/music/01.wav"},
    {"audio": "D:/music/02.wav", "preset": "Clean Bars", "format": "mp4"}
  ],
  "result_path": "D:/output/result.json"
}
```

The result contains success/failed counts, output paths, render time, per-track errors, and details. Missing tracks fail individually. The process exits 0 only when all tracks succeed. `integration/hub_adapter.py` builds this command without assuming any private Hub API.
