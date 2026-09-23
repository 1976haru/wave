from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,time
import numpy as np
from template_system import load_template
from template_system.thumbnails import get_thumbnail
from render.renderer import RendererFactory

def validate(root="templates",output="validation_results"):
    out=Path(output);out.mkdir(parents=True,exist_ok=True);rows=[]
    for path in sorted(Path(root).glob("*.json")):
        try:
            data=load_template(path); thumb,_=get_thumbnail(data); state={"values":np.abs(np.sin(np.linspace(0,3.14, max(8,int(data.get("bands",64))))))}; started=time.perf_counter(); frame=RendererFactory.create("CPU").render_rgba(320,120,state,data); elapsed=time.perf_counter()-started; ok=frame.shape==(120,320,4) and np.isfinite(frame).all(); rows.append({"file":path.name,"id":data.get("id",path.stem),"name":data.get("name_ko",data.get("name")),"category":data.get("category","legacy"),"thumbnail":str(thumb),"ok":bool(ok),"cpu_fps":1/max(elapsed,1e-9)})
        except Exception as exc: rows.append({"file":path.name,"ok":False,"error":repr(exc)})
    report={"count":len(rows),"success":sum(r.get("ok",False) for r in rows),"failed":[r for r in rows if not r.get("ok")],"presets":rows};(out/"preset_validation_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");(out/"preset_validation_report.txt").write_text("\n".join(f"{r['file']}: {'PASS' if r.get('ok') else 'FAIL'}" for r in rows),encoding="utf-8");return report
if __name__=="__main__": print(json.dumps(validate(),ensure_ascii=False,indent=2))
