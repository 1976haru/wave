from __future__ import annotations
import json,time
from pathlib import Path
from .exporter import output_extension,render_audio
class BatchRunner:
    def __init__(self):self.cancelled=False
    def cancel(self):self.cancelled=True
    @staticmethod
    def _write_state(path,state):
        temporary=path.with_suffix(".tmp");temporary.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding="utf-8");temporary.replace(path)
    @staticmethod
    def load_state(path):
        path=Path(path)
        if not path.exists():return {"version":1,"tracks":{}}
        try:return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError,OSError):return {"version":1,"tracks":{}}
    def run(self,files,output_dir,template,options=None,progress=None,render_fn=render_audio,skip_completed=False,state_file=None,progress_detail=None):
        started=time.perf_counter();output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True);state_path=Path(state_file) if state_file else output_dir/"batch_state.json";state=self.load_state(state_path);tracks=state.setdefault("tracks",{});results=[];extension=output_extension(getattr(options,"format","mp4"))
        for source in files:
            key=str(Path(source).resolve());target=output_dir/(Path(source).stem+extension);entry=tracks.setdefault(key,{"file":str(source),"output":str(target),"status":"pending","attempts":0})
            if entry.get("status")=="rendering":entry["status"]="pending"
        self._write_state(state_path,state)
        for index,source in enumerate(files):
            key=str(Path(source).resolve());entry=tracks[key];target=Path(entry["output"])
            if self.cancelled:break
            if skip_completed and entry.get("status")=="completed" and target.exists():results.append({"file":str(source),"status":"skipped","output":str(target)});self._progress(progress,started,index+1,len(files));continue
            entry.update(status="rendering",started_at=time.time(),attempts=int(entry.get("attempts",0))+1);self._write_state(state_path,state)
            try:
                kwargs={"cancel":lambda:self.cancelled}
                if progress_detail: kwargs["progress_detail"]=lambda event, i=index: progress_detail({**event,"track_index":i+1,"track_total":len(files)})
                details=render_fn(source,target,template,options,**kwargs);entry.update(status="completed",completed_at=time.time(),error=None);results.append({"file":str(source),"status":"success",**(details or {})})
            except InterruptedError:
                self.cancelled=True;entry.update(status="cancelled",error="Render cancelled");results.append({"file":str(source),"status":"cancelled"})
            except Exception as exc:
                entry.update(status="failed",error=str(exc));results.append({"file":str(source),"status":"failed","error":str(exc)})
            self._write_state(state_path,state);self._progress(progress,started,index+1,len(files))
        failures=[result for result in results if result["status"]=="failed"]
        if failures:(output_dir/"error_report.json").write_text(json.dumps(failures,indent=2,ensure_ascii=False),encoding="utf-8")
        return results
    @staticmethod
    def _progress(callback,started,done,total):
        if callback:
            elapsed=time.perf_counter()-started;callback(done,total,(elapsed/done)*(total-done))
