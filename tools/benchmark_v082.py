from pathlib import Path
import sys,time,json
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from template_system import load_template
from render.renderer import RendererFactory
names={"Classic White":"01_clean_bars.json","Tokyo Neon":"18_tokyo_neon.json","Chill Ribbon":"23_chill_ribbon.json","Spectrum Ring":"38_spectrum_ring.json","Radial Wave":"40_radial_wave.json","Piano Room":"34_piano_room.json","Blue Jazz":"31_blue_jazz.json"}; vals=np.abs(np.sin(np.linspace(0,9,64)))*.55+.2; state={"values":vals}; report={}
for label,name in names.items():
 t=load_template(Path('templates')/name); start=time.perf_counter(); r=RendererFactory.create('AUTO',t); setup=time.perf_counter()-start; start=time.perf_counter();
 for _ in range(10): r.render_rgba(1920,1080,state,t)
 fps=10/max(time.perf_counter()-start,1e-6); report[label]={"renderer":r.name,"setup_seconds":setup,"fps_1080":fps,"one_hour_minutes":60*30/fps}
Path('validation_results/v082_final_performance_report.json').write_text(json.dumps({"auto":report,"hardware":"ModernGL standalone context"},indent=2),encoding='utf-8'); print(json.dumps(report,indent=2))
