from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,shutil,struct,tempfile,wave
from pathlib import Path
import numpy as np
from audio.analyzer import AnalysisSettings,analyze_file,analyze_pcm
from animation.engine import AnimationEngine
from core.paths import resource_path
from integration.job_contract import validate_job
from pipeline.batch import BatchRunner
from preview.worker import LatestFrameMailbox
from render.renderer import RendererFactory
from template_system import list_templates,load_template
from tools.system_check import check_system
def _record(report,name,fn):
    try:details=fn();report["checks"][name]={"status":"PASS","details":details}
    except Exception as exc:report["checks"][name]={"status":"FAIL","error":repr(exc)}
def _wav(path):
    sr=8000;t=np.arange(sr)/sr;x=(np.sin(2*np.pi*220*t)*16000).astype("<i2")
    with wave.open(str(path),"wb") as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes(x.tobytes())
def validate(output_dir="validation_results",exe=None,run_exports=False):
    root=Path(output_dir);root.mkdir(parents=True,exist_ok=True);report={"version":"0.7.0","checks":{}}
    _record(report,"system",check_system)
    with tempfile.TemporaryDirectory() as temporary:
        temp=Path(temporary);audio=temp/"tone.wav";_wav(audio)
        def cache_check():
            settings=AnalysisSettings(fps=24,bands=16,fft_size=512);first,hit1=analyze_file(audio,settings,temp/"cache");second,hit2=analyze_file(audio,settings,temp/"cache");assert not hit1 and hit2;return {"frames":len(first["spectrum"]),"miss":not hit1,"hit":hit2}
        _record(report,"cache",cache_check)
        features=analyze_pcm(np.sin(2*np.pi*220*np.arange(8000)/8000),8000,fps=24,bands=16,fft_size=512)
        template=load_template(resource_path("templates/01_clean_bars.json"))
        _record(report,"renderer_cpu",lambda:{"shape":list(RendererFactory.create("CPU").render_rgba(320,180,AnimationEngine(features,template).sample(.2),template).shape)})
        def gpu():
            renderer=RendererFactory.create("GPU");image=renderer.render_rgba(320,180,AnimationEngine(features,template).sample(.2),template);return {"renderer":renderer.name,"shape":list(image.shape)}
        _record(report,"renderer_gpu",gpu)
        mailbox=LatestFrameMailbox();mailbox.submit(.1,template);mailbox.submit(.2,template);_record(report,"preview_worker",lambda:{"latest":mailbox.take().seconds,"replaced":mailbox.replaced})
        _record(report,"template_gallery",lambda:{"count":len(list_templates(resource_path("templates")))})
        _record(report,"batch_simulation",lambda:BatchRunner().run([audio,temp/"missing.wav"],temp/"batch",template,render_fn=lambda source,*a,**k:({} if Path(source).exists() else (_ for _ in ()).throw(RuntimeError("expected failure")))))
        _record(report,"job_contract",lambda:validate_job({"tracks":[{"audio":str(audio)}],"output_dir":str(temp),"format":"webm"}))
        if run_exports:
            from pipeline.exporter import ExportOptions,render_audio
            for fmt in ("mp4","webm","mov"):
                _record(report,f"export_{fmt}",lambda fmt=fmt:render_audio(audio,temp/f"smoke.{fmt}",template,ExportOptions(320,180,24,"PREVIEW","CPU",fmt)))
    exe_path=Path(exe or "dist/MusicWaveStudio/MusicWaveStudio.exe");report["checks"]["exe_resources"]={"status":"PASS" if exe_path.exists() else "NOT_TESTED","details":{"path":str(exe_path),"exists":exe_path.exists()}}
    failed=[name for name,data in report["checks"].items() if data["status"]=="FAIL"];report["summary"]={"passed":sum(x["status"]=="PASS" for x in report["checks"].values()),"failed":len(failed),"not_tested":sum(x["status"]=="NOT_TESTED" for x in report["checks"].values()),"failures":failed}
    (root/"final_validation_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8");lines=["Music Wave Studio v0.7 Final Validation"]+[f"{name}: {data['status']}" for name,data in report["checks"].items()];(root/"final_validation_report.txt").write_text("\n".join(lines),encoding="utf-8");return report
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",default="validation_results");p.add_argument("--exe");p.add_argument("--exports",action="store_true");a=p.parse_args();report=validate(a.output,a.exe,a.exports);print(json.dumps(report["summary"],indent=2));return 1 if report["summary"]["failed"] else 0
if __name__=="__main__":raise SystemExit(main())
