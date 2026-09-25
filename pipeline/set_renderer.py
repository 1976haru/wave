from __future__ import annotations
import json, logging, math, subprocess, threading, time
from pathlib import Path
from audio.analyzer import AnalysisSettings, analyze_file
from animation.engine import AnimationEngine
from core.ffmpeg import resolve_ffmpeg
from core.ffmpeg_progress import FFmpegProgressParser
from pipeline.exporter import ExportOptions, build_ffmpeg_command
from render.quality import PRESETS
from render.renderer import RendererFactory

def _hidden(ffmpeg):
    import os
    if os.name != "nt": return {"stdin": subprocess.PIPE, "stderr": subprocess.PIPE}
    si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
    return {"stdin": subprocess.PIPE, "stderr": subprocess.PIPE, "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0), "startupinfo": si}

def render_set(audio_files, target, template, options, timeline_path=None, progress_detail=None, cancel=None):
    """Render an ordered folder of tracks into one continuous video timeline."""
    files = [Path(p) for p in audio_files]
    if not files: raise ValueError("SET에 음원이 없습니다.")
    preset = PRESETS[options.quality]
    logging.info("SET signature stable_preset=%s renderer=%s personality=%s intensity=%s layers=A:main,B:pillars,C:shimmer canvas=%sx%s input_count=%s",template.get("id"),template.get("renderer"),template.get("personality"),template.get("intensity"),options.width,options.height,len(files))
    render_template = dict(template, _quality=options.quality, _glow_scale=preset["glow_scale"], _blur_scale=preset["blur_scale"])
    entries=[]; total_seconds=0.0
    for path in files:
        features, hit = analyze_file(path, AnalysisSettings(fps=options.fps, bands=int(template.get("bands",64))))
        duration=max(float(features["duration"][0]), 0.0)
        entries.append({"path":str(path),"features":features,"duration":duration,"start":total_seconds,"cache_hit":hit})
        total_seconds += duration
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
    proc=subprocess.Popen(build_ffmpeg_command(ffmpeg,target,options,files[0]),**_hidden(ffmpeg)); parser=FFmpegProgressParser(total_seconds); stderr=[]
    def drain():
        for raw in iter(proc.stderr.readline,b""):
            line=raw.decode("utf-8","replace").strip(); stderr.append(line); ev=parser.feed(line)
            if ev and progress_detail: progress_detail(ev)
    reader=threading.Thread(target=drain,daemon=True); reader.start(); engines=[AnimationEngine(e["features"],render_template) for e in entries]; renderer=RendererFactory.create(options.renderer,render_template); started=time.perf_counter()
    try:
        current=0;last_state=None
        for frame_index in range(total_frames):
            if cancel and cancel(): raise InterruptedError("SET 렌더가 중단되었습니다.")
            while current+1<len(entries) and frame_index>=entries[current+1]["start_frame"]:
                current+=1
                if last_state is not None:engines[current].prev=last_state["values"].copy()
            e=entries[current]; local=max(0,frame_index-e["start_frame"])/options.fps
            state=engines[current].sample(local,absolute_seconds=frame_index/options.fps);last_state=state
            frame=renderer.render_rgba(options.width,options.height,state,render_template)
            proc.stdin.write(memoryview(frame))
            if progress_detail:
                progress_detail({"percent":(frame_index+1)/total_frames*100.0,"set_track_index":current+1,"set_track_total":len(entries),"frame":frame_index+1,"fps":(frame_index+1)/max(time.perf_counter()-started,1e-6),"file":Path(e["path"]).name})
        proc.stdin.close(); code=proc.wait(); reader.join(timeout=2)
        if code: raise RuntimeError(f"SET FFmpeg 오류: {' | '.join(stderr[-5:])}")
    except BaseException:
        if proc.stdin and not proc.stdin.closed: proc.stdin.close()
        proc.terminate(); proc.wait(); reader.join(timeout=1)
        if target.exists(): target.unlink()
        raise
    elapsed=time.perf_counter()-started
    return {"output":str(target),"timeline":str(timeline_path) if timeline_path else None,"tracks":len(entries),"duration":total_seconds,"frames":total_frames,"seconds":elapsed,"average_fps":total_frames/max(elapsed,1e-9),"renderer":renderer.name}
