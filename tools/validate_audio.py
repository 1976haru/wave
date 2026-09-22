"""Validate a folder of user audio without committing media files."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audio.analyzer import AnalysisSettings,analyze_file,decode_audio
EXTENSIONS={".wav",".mp3",".flac",".m4a",".ogg",".aac"}
def validate(root,output="validation_results/report.json"):
    root=Path(root);files=[p for p in root.rglob("*") if p.suffix.lower() in EXTENSIONS];results=[];started=time.perf_counter()
    for source in files:
        item={"file":str(source)};begin=time.perf_counter()
        try:
            pcm,sr=decode_audio(source);features,hit=analyze_file(source,AnalysisSettings(fps=24,bands=48));item.update(status="success",sample_rate=sr,duration_seconds=len(pcm)/sr,frames=len(features["spectrum"]),cache_hit=hit,seconds=time.perf_counter()-begin)
        except Exception as exc:item.update(status="failed",error=str(exc),seconds=time.perf_counter()-begin)
        results.append(item);print(f"[{len(results)}/{len(files)}] {item['status']}: {source.name}")
    report={"root":str(root),"total":len(files),"success":sum(r["status"]=="success" for r in results),"failed":sum(r["status"]=="failed" for r in results),"elapsed_seconds":time.perf_counter()-started,"results":results};target=Path(output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8");return report
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("folder");parser.add_argument("--output",default="validation_results/report.json");args=parser.parse_args();validate(args.folder,args.output)
