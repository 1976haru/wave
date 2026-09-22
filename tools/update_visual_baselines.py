"""Explicitly regenerate deterministic CPU visual baselines."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2,numpy as np
from render.renderer import CPURenderer
from template_system import DEFAULT_TEMPLATE
CASES={"bars":{},"line":{"renderer":"line"},"dot":{"renderer":"dot"},"mirror":{"mirror":True,"position":"center"},"gradient":{"gradient":True,"gradient_start":"#FF3355","gradient_end":"#3388FF"},"glow":{"glow":True,"glow_radius":6,"glow_strength":.5},"opacity":{"opacity":.45},"roundness":{"roundness":1.0}}
def render_case(changes):
    template=dict(DEFAULT_TEMPLATE,glow=False,bands=32,color="#DDEEFF",width=.8,height=.35);template.update(changes);values=(np.sin(np.linspace(0,np.pi*3,32))*.35+.55).astype(np.float32);return CPURenderer().render_rgba(320,180,{"values":values},template)
def main():
    root=Path("tests/baselines");root.mkdir(parents=True,exist_ok=True)
    for name,changes in CASES.items():cv2.imwrite(str(root/f"{name}.png"),cv2.cvtColor(render_case(changes),cv2.COLOR_RGBA2BGRA))
if __name__=="__main__":main()
