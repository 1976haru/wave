from __future__ import annotations
import shutil
from pathlib import Path
def resolve_ffmpeg(selected=None,application_dir=None):
    candidates=[]
    if selected:candidates.append(Path(selected))
    if application_dir:candidates.extend([Path(application_dir)/"ffmpeg.exe",Path(application_dir)/"bin"/"ffmpeg.exe"])
    found=shutil.which("ffmpeg")
    if found:candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():return str(candidate)
    return None
def resolve_ffprobe(ffmpeg_path=None):
    if ffmpeg_path:
        candidate=Path(ffmpeg_path).with_name("ffprobe.exe")
        if candidate.is_file():return str(candidate)
    return shutil.which("ffprobe")
