"""Memory saver mode ("메모리 절약 모드"): one process-wide switch plus SET-boundary housekeeping.

The UI owns the persisted value and calls set_enabled(); render/analysis code only
reads the derived profile, so users never tune chunk sizes, caches or GC directly.
One-track-at-a-time SET rendering is the common structure in both modes.
"""
from __future__ import annotations
import gc,logging,os,threading,time

ENV="MWS_MEMORY_SAVER"
LOW_CHUNK_FRAMES=128
NORMAL_CHUNK_FRAMES=384
GUARD_AVAILABLE_MB=2048.0
GUARD_MAX_WAIT_SECONDS=120.0
_lock=threading.Lock()
_enabled=os.environ.get(ENV,"1")!="0"

def is_enabled()->bool:return _enabled

def set_enabled(value:bool)->None:
    global _enabled
    with _lock:
        changed=_enabled!=bool(value);_enabled=bool(value)
    if changed:logging.info("MEMORY saver_mode=%s",_enabled)

def analysis_chunk_frames()->int:return LOW_CHUNK_FRAMES if _enabled else NORMAL_CHUNK_FRAMES

def isolate_analysis()->bool:
    """Run cache-miss analysis in a short-lived subprocess so its NumPy/SciPy heap goes back to Windows."""
    return _enabled

def cooldown_seconds()->float:return 1.5 if _enabled else 0.3

def guard_available_mb()->float:return float(os.environ.get("MWS_GUARD_AVAILABLE_MB",GUARD_AVAILABLE_MB))

def live_ffmpeg_children()->list[int]:
    """PIDs of FFmpeg/FFprobe processes still parented to this process (should be empty at a SET boundary)."""
    try:
        import psutil
        return [child.pid for child in psutil.Process().children(recursive=True) if child.name().lower().startswith(("ffmpeg","ffprobe"))]
    except Exception:return []

def set_boundary(next_set:int,cancel=None,notify=None,sleep=time.sleep)->dict:
    """Strong cleanup + cool-down before the next SET; in saver mode also wait (bounded) for free RAM.

    Never interrupts a running render: it only runs between SETs.
    """
    from core.memory_telemetry import checkpoint
    gc.collect();leftovers=live_ffmpeg_children()
    if leftovers:logging.warning("MEMORY set_boundary ffmpeg_children=%s",leftovers)
    sleep(cooldown_seconds())
    data=checkpoint("set_cooldown",next_set=next_set,saver=int(_enabled),ffmpeg_children=len(leftovers));waited=0.0
    threshold=guard_available_mb()
    while _enabled and data.get("available_mb") is not None and data["available_mb"]<threshold and waited<GUARD_MAX_WAIT_SECONDS:
        if cancel and cancel():break
        if notify:notify({"memory_warning":"사용 가능한 메모리가 부족합니다. 현재 작업이 끝난 뒤 다음 예약 작업을 잠시 대기합니다."})
        sleep(5.0);waited+=5.0;gc.collect();data=checkpoint("set_memory_wait",next_set=next_set,waited_s=int(waited))
    data["waited_seconds"]=waited;data["ffmpeg_children"]=leftovers
    return data
