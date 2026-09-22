"""Measure AnimationEngine and CPU renderer stages per frame."""
from __future__ import annotations
import argparse,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from animation.engine import AnimationEngine
from render.renderer import CPURenderer
from template_system import load_template

def profile_template(path,frames=60,width=1920,height=1080,quality="BALANCED"):
    template=dict(load_template(path),_quality=quality);bands=int(template["bands"]);features={"spectrum":np.abs(np.sin(np.linspace(0,8,frames*bands))).reshape(frames,bands).astype(np.float32),"rms":np.ones(frames),"bass":np.ones(frames),"mid":np.ones(frames),"high":np.ones(frames),"onset":np.zeros(frames),"fps":np.array([30])};engine=AnimationEngine(features,template);renderer=CPURenderer();animation=0;stages={};total=time.perf_counter()
    for index in range(frames):
        mark=time.perf_counter();state=engine.sample(index/30);animation+=time.perf_counter()-mark;renderer.render_rgba(width,height,state,template)
        for key,value in renderer.last_profile.items():stages[key]=stages.get(key,0)+value
    elapsed=time.perf_counter()-total;return {"template":template["name"],"frames":frames,"fps":frames/elapsed,"animation_ms_per_frame":animation*1000/frames,"renderer_stages_ms_per_frame":{key:value/frames for key,value in stages.items()},"total_seconds":elapsed}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--frames",type=int,default=60);parser.add_argument("--output",default="validation_results/render_profile.json");args=parser.parse_args();report={"profiles":[profile_template("templates/04_tokyo_night.json",args.frames),profile_template("templates/07_mirror_spectrum.json",args.frames)]};target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report,indent=2))
if __name__=="__main__":main()
