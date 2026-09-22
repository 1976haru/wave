"""Renderer benchmark for preview, landscape and portrait targets."""
from __future__ import annotations
import argparse,json,time,tracemalloc,sys,shutil,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from render.renderer import RendererFactory
from template_system import load_template
SCENARIOS=(("PREVIEW",960,540,24),("LANDSCAPE",1920,1080,30),("PORTRAIT",1080,1920,30));TEMPLATES=("01_clean_bars.json","04_tokyo_night.json","07_mirror_spectrum.json")
def benchmark(renderer_name,width,height,template,frames):
    try:renderer=RendererFactory.create(renderer_name)
    except Exception as exc:return {"status":"unavailable","error":str(exc)}
    times=[];tracemalloc.start()
    for index in range(frames):
        values=(np.abs(np.sin(np.linspace(0,8,template["bands"])+index*.13))*.85+.05).astype(np.float32);started=time.perf_counter();renderer.render_rgba(width,height,{"values":values},template);times.append(time.perf_counter()-started)
    peak=tracemalloc.get_traced_memory()[1]/(1024*1024);tracemalloc.stop();total=sum(times);fps=frames/max(total,1e-9);return {"status":"success","renderer":renderer.name,"frames":frames,"seconds":total,"fps":fps,"average_frame_ms":1000*total/frames,"p95_frame_ms":1000*float(np.percentile(times,95)),"peak_memory_mb":peak,"estimated_one_minute_render_seconds":1800/fps,"estimated_one_hour_render_minutes":108000/fps/60,"realtime_ratio":fps/30}
def benchmark_encode(width,height,fps,frames):
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:return {"status":"unavailable"}
    frame=np.zeros((height,width,4),np.uint8).tobytes();command=[ffmpeg,"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s",f"{width}x{height}","-r",str(fps),"-i","pipe:0","-frames:v",str(frames),"-c:v","libx264","-preset","veryfast","-f","null","NUL"]
    started=time.perf_counter();process=subprocess.Popen(command,stdin=subprocess.PIPE)
    for _ in range(frames):process.stdin.write(frame)
    process.stdin.close();code=process.wait();elapsed=time.perf_counter()-started;return {"status":"success" if code==0 else "failed","seconds":elapsed,"fps":frames/max(elapsed,1e-9),"average_frame_ms":elapsed*1000/frames}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--frames",type=int,default=30);parser.add_argument("--output",default="validation_results/render_benchmark.json");args=parser.parse_args();results=[];encoders=[]
    for scenario,width,height,fps in SCENARIOS:
        encode=benchmark_encode(width,height,fps,args.frames);encode.update(scenario=scenario,width=width,height=height,target_fps=fps);encoders.append(encode)
        for filename in TEMPLATES:
            template=load_template(Path("templates")/filename)
            for renderer in ("CPU","GPU"):
                result=benchmark(renderer,width,height,template,args.frames);result.update(scenario=scenario,width=width,height=height,target_fps=fps,template=template["name"],requested_renderer=renderer);results.append(result);print(scenario,template["name"],renderer,result.get("fps",result.get("status")))
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps({"render_results":results,"ffmpeg_encode_results":encoders},indent=2),encoding="utf-8")
if __name__=="__main__":main()
