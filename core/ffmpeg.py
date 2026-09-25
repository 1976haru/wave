from __future__ import annotations
import shutil,sys
from pathlib import Path
def resolve_ffmpeg(selected=None,application_dir=None):
    candidates=[]
    if selected:candidates.append(Path(selected))
    roots=[]
    if application_dir: roots.append(Path(application_dir))
    roots.extend([Path(getattr(sys,"_MEIPASS",Path(sys.executable).resolve().parent)),Path(sys.executable).resolve().parent])
    for root in roots: candidates.extend([root/"ffmpeg.exe",root/"bin"/"ffmpeg.exe"])
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
