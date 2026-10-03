from __future__ import annotations
import gc, json, logging, math, subprocess, threading, time
from collections import deque
from pathlib import Path
from audio.analyzer import AnalysisSettings, analysis_duration, analyze_file
from animation.engine import AnimationEngine
from core.ffmpeg import resolve_ffmpeg
from core.memory_telemetry import checkpoint as memory_checkpoint, low_memory_message
from core.ffmpeg_progress import FFmpegProgressParser
from pipeline.exporter import ExportOptions, build_ffmpeg_command, release_process as _release_process
from render.quality import PRESETS
from render.renderer import RendererFactory, release_renderer
from visualizers.background_source import source_from_template

def _hidden(ffmpeg):
    import os
    if os.name != "nt": return {"stdin": subprocess.PIPE, "stderr": subprocess.PIPE}
    si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
    return {"stdin": subprocess.PIPE, "stderr": subprocess.PIPE, "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0), "startupinfo": si}

def _memory_event(progress_detail, stage, **extra):
    data=memory_checkpoint(stage, **extra); message=low_memory_message(data)
    if message and progress_detail: progress_detail({"memory_warning":message})
    return data

def render_set(audio_files, target, template, options, timeline_path=None, progress_detail=None, cancel=None):
    """Render an ordered folder of tracks into one continuous video timeline.

    Only lightweight metadata (path/duration/frame range) is kept for the whole
    SET; analysis features and the AnimationEngine exist for one track at a time.
    """
    files = [Path(p) for p in audio_files]
    if not files: raise ValueError("SET에 음원이 없습니다.")
    preset = PRESETS[options.quality]
    logging.info("SET signature stable_preset=%s renderer=%s personality=%s intensity=%s layers=A:main,B:pillars,C:shimmer canvas=%sx%s input_count=%s",template.get("id"),template.get("renderer"),template.get("personality"),template.get("intensity"),options.width,options.height,len(files))
    render_template = dict(template, _quality=options.quality, _glow_scale=preset["glow_scale"], _blur_scale=preset["blur_scale"])
    settings = AnalysisSettings(fps=options.fps, bands=int(template.get("bands",64)))
    _memory_event(progress_detail, "set_start", tracks=len(files))
    entries=[]; total_seconds=0.0
    for path in files:
        if cancel and cancel(): raise InterruptedError("SET 렌더가 중단되었습니다.")
        duration, hit = analysis_duration(path, settings)
        duration=max(duration, 0.0)
        entries.append({"path":str(path),"duration":duration,"start":total_seconds,"cache_hit":hit})
        total_seconds += duration
    gc.collect()
    total_frames=max(1,int(round(total_seconds*options.fps)))
    for i,e in enumerate(entries):
        e["start_frame"] = int(round(e["start"]*options.fps))
        e["end_frame"] = int(round((e["start"]+e["duration"])*options.fps))-1
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    timeline=[{"index":i+1,"file":Path(e["path"]).name,"start":e["start"],"duration":e["duration"],"start_time":time.strftime('%H:%M:%S',time.gmtime(e["start"]))} for i,e in enumerate(entries)]
    if timeline_path:
        Path(timeline_path).write_text(json.dumps({"fps":options.fps,"total_duration":total_seconds,"total_frames":total_frames,"tracks":timeline},indent=2,ensure_ascii=False),encoding="utf-8")
    ffmpeg=resolve_ffmpeg(options.ffmpeg_path)
    if not ffmpeg: raise RuntimeError("FFmpeg가 필요합니다.")
    proc=reader=renderer=background_source=None; features=engine=state=frame=background=None; succeeded=False; renderer_name=""
    stderr=deque(maxlen=200)
    try:
        proc=subprocess.Popen(build_ffmpeg_command(ffmpeg,target,options,files[0]),**_hidden(ffmpeg)); parser=FFmpegProgressParser(total_seconds)
        def drain():
            for raw in iter(proc.stderr.readline,b""):
                line=raw.decode("utf-8","replace").strip(); stderr.append(line); ev=parser.feed(line)
                if ev and progress_detail: progress_detail(ev)
        reader=threading.Thread(target=drain,daemon=True,name="mws-set-ffmpeg-stderr"); reader.start()
        renderer=RendererFactory.create(options.renderer,render_template); renderer_name=renderer.name; background_source=source_from_template(render_template); started=time.perf_counter()
        current=-1; last_values=None; last_emit=0.0
        for frame_index in range(total_frames):
            if cancel and cancel(): raise InterruptedError("SET 렌더가 중단되었습니다.")
            wanted=max(current,0)
            while wanted+1<len(entries) and frame_index>=entries[wanted+1]["start_frame"]: wanted+=1
            if wanted!=current:
                if engine is not None:
                    _memory_event(progress_detail, "track_end", track=current+1)
                    engine=features=state=None; gc.collect()
                features,_hit=analyze_file(entries[wanted]["path"], settings); engine=AnimationEngine(features,render_template)
                if last_values is not None: engine.prev=last_values.copy()
                current=wanted; _memory_event(progress_detail, "track_start", track=current+1, total=len(entries))
            e=entries[current]; local=max(0,frame_index-e["start_frame"])/options.fps
            absolute_seconds=frame_index/options.fps;state=engine.sample(local,absolute_seconds=absolute_seconds);last_values=state["values"]
            if background_source:
                background=background_source.frame(absolute_seconds,options.width,options.height)
                if background is not None:state["background_frame"]=background
            frame=renderer.render_rgba(options.width,options.height,state,render_template)
            proc.stdin.write(memoryview(frame))
            now=time.perf_counter()
            if progress_detail and (now-last_emit>=.1 or frame_index+1==total_frames):
                last_emit=now; progress_detail({"percent":(frame_index+1)/total_frames*100.0,"set_track_index":current+1,"set_track_total":len(entries),"frame":frame_index+1,"fps":(frame_index+1)/max(now-started,1e-6),"file":Path(e["path"]).name})
        if engine is not None: _memory_event(progress_detail, "track_end", track=current+1)
        engine=features=state=frame=background=last_values=None
        proc.stdin.close(); code=proc.wait(); reader.join(timeout=2)
        if code: raise RuntimeError(f"SET FFmpeg 오류: {' | '.join(list(stderr)[-5:])}")
        succeeded=True
    finally:
        # One cleanup path for success, failure and cancel.
        _release_process(proc, reader)
        if background_source: background_source.close()
        release_renderer(renderer)
        proc=reader=renderer=background_source=features=engine=state=frame=background=None
        if not succeeded and target.exists():
            try: target.unlink()
            except OSError: logging.exception("SET partial output cleanup failed path=%s", target)
        gc.collect()
        _memory_event(progress_detail, "set_end", ok=succeeded)
    elapsed=time.perf_counter()-started
    return {"output":str(target),"timeline":str(timeline_path) if timeline_path else None,"tracks":len(entries),"duration":total_seconds,"frames":total_frames,"seconds":elapsed,"average_fps":total_frames/max(elapsed,1e-9),"renderer":renderer_name}
