from __future__ import annotations
import shutil, subprocess
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from audio.analyzer import AnalysisSettings, analyze_file
from animation.engine import AnimationEngine
from render.renderer import RendererFactory
from render.quality import PRESETS

@dataclass
class ExportOptions:
    width:int=1920; height:int=1080; quality:str="BALANCED"; renderer:str="AUTO"; format:str="mp4"

def _command(ffmpeg,output,options,fps,audio):
    common=[ffmpeg,"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s",f"{options.width}x{options.height}","-r",str(fps),"-i","pipe:0","-i",str(audio),"-shortest"]
    suffix=output.suffix.lower()
    if suffix==".webm": return common+["-c:v","libvpx-vp9","-pix_fmt","yuva420p","-auto-alt-ref","0","-c:a","libopus",str(output)]
    if suffix==".mov": return common+["-c:v","prores_ks","-profile:v","4","-pix_fmt","yuva444p10le","-c:a","pcm_s16le",str(output)]
    return common+["-vf","format=rgb24","-c:v","libx264","-pix_fmt","yuv420p","-crf",str(PRESETS[options.quality]["crf"]),"-c:a","aac",str(output)]

def render_audio(audio_path,output_path,template,options=None,progress=None,cancel=None,logger=print):
    options=options or ExportOptions(); preset=PRESETS[options.quality]; settings=AnalysisSettings(fps=preset["fps"],bands=int(template.get("bands",64)))
    features,hit=analyze_file(audio_path,settings,logger=logger); engine=AnimationEngine(features,template); renderer=RendererFactory.create(options.renderer)
    ffmpeg=shutil.which("ffmpeg");
    if not ffmpeg: raise RuntimeError("FFmpeg is required for video export")
    output=Path(output_path); output.parent.mkdir(parents=True,exist_ok=True); fps=int(preset["fps"]); total=max(1,int(float(features["duration"][0])*fps)); started=perf_counter()
    process=subprocess.Popen(_command(ffmpeg,output,options,fps,audio_path),stdin=subprocess.PIPE)
    try:
        for frame in range(total):
            if cancel and cancel(): raise InterruptedError("Render cancelled")
            rgba=renderer.render_rgba(options.width,options.height,engine.sample(frame/fps),template); process.stdin.write(rgba.tobytes())
            if progress: progress(frame+1,total)
        process.stdin.close(); code=process.wait()
        if code: raise RuntimeError(f"FFmpeg exited with code {code}")
    except BaseException:
        if process.stdin and not process.stdin.closed: process.stdin.close()
        process.terminate(); process.wait();
        if output.exists(): output.unlink()
        raise
    elapsed=perf_counter()-started; logger(f"render renderer={renderer.name} frames={total} time={elapsed:.3f}s average_fps={total/max(elapsed,1e-6):.2f} cache={'hit' if hit else 'miss'}")
    return {"output":str(output),"renderer":renderer.name,"cache_hit":hit,"frames":total,"seconds":elapsed}
