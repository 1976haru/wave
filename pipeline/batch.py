from __future__ import annotations
import json, time
from pathlib import Path
from .exporter import render_audio
class BatchRunner:
    def __init__(self): self.cancelled=False
    def cancel(self): self.cancelled=True
    def run(self,files,output_dir,template,options=None,progress=None,render_fn=render_audio):
        started=time.perf_counter(); output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True); results=[]
        for index,source in enumerate(files):
            if self.cancelled: break
            try:
                extension={"webm":".webm","mov":".mov"}.get(getattr(options,"format","mp4"),".mp4"); target=output_dir/(Path(source).stem+extension)
                details=render_fn(source,target,template,options,cancel=lambda:self.cancelled); results.append({"file":str(source),"status":"success",**(details or {})})
            except InterruptedError: self.cancelled=True; results.append({"file":str(source),"status":"cancelled"})
            except Exception as exc: results.append({"file":str(source),"status":"failed","error":str(exc)})
            if progress:
                elapsed=time.perf_counter()-started; done=index+1; progress(done,len(files),(elapsed/done)*(len(files)-done))
        failures=[r for r in results if r["status"]=="failed"]
        if failures: (output_dir/"error_report.json").write_text(json.dumps(failures,indent=2,ensure_ascii=False),encoding="utf-8")
        return results
