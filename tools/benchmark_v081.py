from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,time
import numpy as np
from template_system import load_template
from render.renderer import RendererFactory,CPURenderer

def bench(path,w,h,choice,frames=20):
    t=load_template(path); vals=np.abs(np.sin(np.linspace(0,9,64)))*.55+.2; state={"values":vals}; start=time.perf_counter(); mode=""
    try:
        r=RendererFactory.create(choice); mode=getattr(r,"name",choice)
        for _ in range(frames): r.render_rgba(w,h,state,t)
        fps=frames/max(time.perf_counter()-start,1e-6); return {"fps":fps,"mode":mode,"error":None}
    except Exception as exc:return {"fps":0,"mode":"FAIL","error":repr(exc)}

def main():
    names={"Tokyo Neon":"18_tokyo_neon.json","Chill Ribbon":"23_chill_ribbon.json","Spectrum Ring":"38_spectrum_ring.json","Radial Wave":"40_radial_wave.json","Piano Room":"34_piano_room.json","Classic White Bars":"01_clean_bars.json","Blue Jazz":"31_blue_jazz.json"}; report={"gpu":{},"preview":{},"encode":{},"gpu_context":"unknown"}
    for label,name in names.items():
        report["preview"][label]=bench(Path("templates")/name,960,540,"AUTO",20); report["gpu"][label]={"cpu":bench(Path("templates")/name,1920,1080,"CPU",5),"gpu":bench(Path("templates")/name,1920,1080,"GPU",5)}
    Path("validation_results").mkdir(exist_ok=True); Path("validation_results/v081_performance_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8"); print(json.dumps(report,indent=2))
if __name__=="__main__":main()

