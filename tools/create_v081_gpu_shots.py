from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from template_system import load_template
from render.renderer import RendererFactory,CPURenderer
vals=np.abs(np.sin(np.linspace(0,9,64)))*.55+.2; vals[::7]=.9
for ident,label in [("18_tokyo_neon","tokyo_neon"),("23_chill_ribbon","chill_ribbon"),("38_spectrum_ring","spectrum_ring"),("40_radial_wave","radial_wave")]:
 t=load_template(Path("templates")/(ident+".json")); state={"values":vals}
 for choice,prefix in [("GPU","v081_gpu_"),("CPU","v081_cpu_")]:
  try: img=RendererFactory.create(choice).render_rgba(960,540,state,t); Image.fromarray(img,"RGBA").save(f"validation_results/{prefix}{label}.png")
  except Exception as exc: print(choice,ident,exc)

