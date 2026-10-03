"""Short-lived analysis process: analyse one track into the cache, then exit.

argv: <audio path> <AnalysisSettings json> <cache dir> <chunk frames>
Started by audio.analyzer.analyze_isolated (``python -m audio.analysis_worker`` or
``MusicWaveStudio.exe --analysis-worker``). Writes nothing but the cache entry.
"""
from __future__ import annotations
import json,os,sys

def _emit(text:str)->None:
    # Windowed (noconsole) builds may have sys.stderr=None; write to the inherited handle directly.
    try:os.write(2,(text+"\n").encode("utf-8","replace"))
    except OSError:pass

def main(argv=None)->int:
    for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ.setdefault(name,"1")
    args=list(sys.argv[1:] if argv is None else argv)
    if len(args)!=4:
        print("usage: analysis_worker <audio> <settings-json> <cache-dir> <chunk-frames>",file=sys.stderr);return 2
    from audio.analyzer import WORKER_OK,AnalysisSettings,_cache_entry,_cache_valid,analyze_file
    path,settings_json,cache_dir,chunk=args
    try:
        settings=AnalysisSettings(**json.loads(settings_json))
        analyze_file(path,settings,cache_dir,chunk_frames=int(chunk),isolate=False)
        _key,target,meta_path,expected=_cache_entry(path,settings,cache_dir)
        if _cache_valid(target,meta_path,expected) is None:raise RuntimeError(f"cache not written: {target}")
    except Exception as exc:
        _emit(f"{type(exc).__name__}: {exc}");return 1
    # The parent requires this marker: exit code 0 alone could come from a non-worker launch.
    _emit(WORKER_OK);return 0

if __name__=="__main__":raise SystemExit(main())
