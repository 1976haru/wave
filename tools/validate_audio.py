"""Validate up to 15 user audio files and measure cold/warm analysis."""
from __future__ import annotations
import argparse,json,shutil,subprocess,sys,time,tracemalloc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from audio.analyzer import AnalysisSettings,analyze_file,cache_key,decode_audio
from animation.engine import AnimationEngine
from render.renderer import CPURenderer,RendererFactory
from template_system import load_template
EXTENSIONS={".wav",".mp3",".flac",".m4a",".ogg",".aac"}
def probe(path):
    if not shutil.which("ffprobe"):return {}
    process=subprocess.run([shutil.which("ffprobe"),"-v","error","-select_streams","a:0","-show_entries","stream=codec_name,sample_rate,channels,duration","-of","json",str(path)],capture_output=True,text=True)
    try:return json.loads(process.stdout).get("streams",[{}])[0]
    except Exception:return {}
def preview_benchmark(features,template,renderer,frames=48):
    engine=AnimationEngine(features,template);started=time.perf_counter()
    for index in range(min(frames,len(features["spectrum"]))):renderer.render_rgba(480,270,engine.sample(index/24),template)
    count=min(frames,len(features["spectrum"]));elapsed=time.perf_counter()-started;return count/max(elapsed,1e-9)
def validate(root,output="validation_results/validation_report.json",limit=15):
    root=Path(root);files=sorted(p for p in root.rglob("*") if p.suffix.lower() in EXTENSIONS);files=files if limit==0 else files[:limit];results=[];total_started=time.perf_counter();settings=AnalysisSettings(fps=24,bands=48);cache_dir=Path("validation_results/cache");template=load_template("templates/01_clean_bars.json");cpu_renderer=CPURenderer()
    try:gpu_renderer=RendererFactory.create("GPU")
    except Exception:gpu_renderer=None
    for source in files:
        item={"file":str(source),"name":source.name};started=time.perf_counter();tracemalloc.start()
        try:
            metadata=probe(source);pcm,sr=decode_audio(source);duration=len(pcm)/sr;target=cache_dir/f"{cache_key(source,settings)}.npz";target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():target.unlink()
            cold=time.perf_counter();features,_=analyze_file(source,settings,cache_dir);cold=time.perf_counter()-cold;warm=time.perf_counter();_,hit=analyze_file(source,settings,cache_dir);warm=time.perf_counter()-warm;cpu_fps=preview_benchmark(features,template,cpu_renderer);gpu_fps=preview_benchmark(features,template,gpu_renderer) if gpu_renderer else None;peak=tracemalloc.get_traced_memory()[1]/(1024*1024);cpu_final=max(.1,cpu_fps*(480*270)/(1920*1080));gpu_final=max(.1,gpu_fps*(480*270)/(1920*1080)) if gpu_fps else None;item.update(status="success",decode_success=True,codec=metadata.get("codec_name","unknown"),duration_seconds=duration,sample_rate=int(metadata.get("sample_rate",sr)),channels=int(metadata.get("channels",1)),analysis_cache_miss_seconds=cold,analysis_cache_hit_seconds=warm,cache_hit=hit,cache_speedup=cold/max(warm,1e-9),peak_memory_mb=peak,preview_cpu_fps=cpu_fps,preview_gpu_fps=gpu_fps,estimated_final_cpu_fps=cpu_final,estimated_final_gpu_fps=gpu_final,estimated_final_cpu_seconds=duration/cpu_final*30,estimated_final_gpu_seconds=duration/gpu_final*30 if gpu_final else None)
        except Exception as exc:item.update(status="failed",decode_success=False,error=str(exc))
        finally:tracemalloc.stop()
        item["validation_seconds"]=time.perf_counter()-started;results.append(item);print(f"[{len(results)}/{len(files)}] {item['status']}: {source.name}")
    successes=[r for r in results if r["status"]=="success"];report={"root":str(root),"total_tracks":len(files),"successful_tracks":len(successes),"failed_tracks":len(files)-len(successes),"failed_files":[r["file"] for r in results if r["status"]=="failed"],"total_duration_seconds":sum(r.get("duration_seconds",0) for r in successes),"total_analysis_seconds":sum(r.get("analysis_cache_miss_seconds",0) for r in successes),"average_cache_speedup":float(np.mean([r["cache_speedup"] for r in successes])) if successes else 0,"estimated_batch_render_seconds":sum(r.get("estimated_final_cpu_seconds",0) for r in successes),"estimated_batch_gpu_seconds":sum(r.get("estimated_final_gpu_seconds") or 0 for r in successes) if any(r.get("estimated_final_gpu_seconds") for r in successes) else None,"validation_elapsed_seconds":time.perf_counter()-total_started,"results":results};target=Path(output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8");text=target.with_suffix(".txt");text.write_text("Music Wave Studio Audio Validation\n"+"="*36+"\n"+"\n".join(f"{key}: {value}" for key,value in report.items() if key!="results")+"\n\n"+"\n".join(f"{r['status'].upper():7} {r['name']} {r.get('duration_seconds',0):.2f}s {r.get('analysis_cache_miss_seconds',0):.3f}s" for r in results),encoding="utf-8");return report
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("folder");parser.add_argument("--output",default="validation_results/user_audio_validation.json");parser.add_argument("--all",action="store_true");parser.add_argument("--limit",type=int,default=15);args=parser.parse_args();validate(args.folder,args.output,0 if args.all else args.limit)
