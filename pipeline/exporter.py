from __future__ import annotations
import math,shutil,subprocess,os,threading
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from audio.analyzer import AnalysisSettings,analyze_file
from core.ffmpeg import resolve_ffmpeg
from core.ffmpeg_progress import FFmpegProgressParser
from animation.engine import AnimationEngine
from render.renderer import RendererFactory
from render.quality import PRESETS
RESOLUTIONS={"1920x1080":(1920,1080),"1080x1920":(1080,1920),"1080x1080":(1080,1080)}
@dataclass
class ExportOptions:
    width:int=1920;height:int=1080;fps:int=30;quality:str="BALANCED";renderer:str="AUTO";format:str="mp4";ffmpeg_path:str|None=None
    @classmethod
    def from_resolution(cls,resolution="1920x1080",**kwargs):
        width,height=RESOLUTIONS.get(resolution,(kwargs.pop("width",1920),kwargs.pop("height",1080)));return cls(width=width,height=height,**kwargs)
def output_extension(format_name):return {"mp4":".mp4","webm":".webm","mov":".mov"}[format_name.lower()]
def build_ffmpeg_command(ffmpeg,output,options,audio):
    preset=PRESETS[options.quality];common=[ffmpeg,"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s",f"{options.width}x{options.height}","-r",str(options.fps),"-i","pipe:0","-i",str(audio),"-shortest"];suffix=Path(output).suffix.lower()
    if suffix==".webm":return common+["-progress","pipe:2","-nostats","-c:v","libvpx-vp9","-pix_fmt","yuva420p","-auto-alt-ref","0","-deadline","realtime" if options.quality=="PREVIEW" else "good","-c:a","libopus",str(output)]
    if suffix==".mov":return common+["-progress","pipe:2","-nostats","-c:v","prores_ks","-profile:v","4","-pix_fmt","yuva444p10le","-c:a","pcm_s16le",str(output)]
    return common+["-progress","pipe:2","-nostats","-vf","format=rgb24","-c:v","libx264","-preset",preset["encoder_preset"],"-pix_fmt","yuv420p","-crf",str(preset["crf"]),"-c:a","aac",str(output)]
def _hidden_process_kwargs():
    if os.name != "nt": return {"stdin": subprocess.PIPE, "stderr": subprocess.PIPE}
    flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
    startup=subprocess.STARTUPINFO(); startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow=0
    return {"stdin":subprocess.PIPE,"stderr":subprocess.PIPE,"creationflags":flags,"startupinfo":startup}

def render_audio(audio_path,output_path,template,options=None,progress=None,cancel=None,logger=print,progress_detail=None):
    options=options or ExportOptions();preset=PRESETS[options.quality];render_template=dict(template,_quality=options.quality,_glow_scale=preset["glow_scale"],_blur_scale=preset["blur_scale"]);features,hit=analyze_file(audio_path,AnalysisSettings(fps=options.fps,bands=int(template.get("bands",64))),logger=logger);engine=AnimationEngine(features,render_template);renderer=RendererFactory.create(options.renderer,render_template);ffmpeg=resolve_ffmpeg(options.ffmpeg_path)
    if not ffmpeg:raise RuntimeError("FFmpeg is required for video export")
    output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True);duration=max(float(features["duration"][0]),1e-6);total=max(1,math.ceil(duration*options.fps));started=perf_counter();animation_seconds=renderer_seconds=pipe_seconds=0.0;parser=FFmpegProgressParser(duration);stderr_lines=[]
    process=subprocess.Popen(build_ffmpeg_command(ffmpeg,output,options,audio_path),**_hidden_process_kwargs())
    def read_progress():
        for raw in iter(process.stderr.readline,b""):
            line=raw.decode("utf-8","replace").strip(); stderr_lines.append(line)
            event=parser.feed(line)
            if event and progress_detail: progress_detail(event)
    reader=threading.Thread(target=read_progress,daemon=True);reader.start()
    try:
        for frame_index in range(total):
            if cancel and cancel():raise InterruptedError("Render cancelled")
            mark=perf_counter();state=engine.sample(frame_index/options.fps);animation_seconds+=perf_counter()-mark;mark=perf_counter();frame=renderer.render_rgba(options.width,options.height,state,render_template);renderer_seconds+=perf_counter()-mark;mark=perf_counter();process.stdin.write(memoryview(frame));pipe_seconds+=perf_counter()-mark
        process.stdin.close();mark=perf_counter();code=process.wait();encode_wait_seconds=perf_counter()-mark;reader.join(timeout=2)
        if code:raise RuntimeError(f"FFmpeg exited with code {code}: {" | ".join(stderr_lines[-5:])}")
        if progress_detail: progress_detail({"percent":100.0,"out_time":duration,"frame":total,"fps":total/max(perf_counter()-started,1e-9),"done":True})
    except BaseException:
        if process.stdin and not process.stdin.closed:process.stdin.close()
        process.terminate();process.wait();reader.join(timeout=1)
        if output.exists():output.unlink()
        raise
    elapsed=perf_counter()-started;generation=animation_seconds+renderer_seconds;frame_generation_fps=total/max(generation,1e-9);average_fps=total/max(elapsed,1e-9);bottleneck="Encoder" if pipe_seconds+encode_wait_seconds>renderer_seconds else "Renderer";profile={"animation_seconds":animation_seconds,"renderer_seconds":renderer_seconds,"pipe_write_seconds":pipe_seconds,"encode_wait_seconds":encode_wait_seconds,"frame_generation_fps":frame_generation_fps,"average_fps":average_fps,"bottleneck":bottleneck}
    logger(f"render renderer={renderer.name} frames={total} total={elapsed:.3f}s generation_fps={frame_generation_fps:.2f} output_fps={average_fps:.2f} bottleneck={bottleneck} cache={'hit' if hit else 'miss'}");return {"output":str(output),"renderer":renderer.name,"cache_hit":hit,"frames":total,"seconds":elapsed,**profile}

