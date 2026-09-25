from pathlib import Path
import json
import numpy as np
from render.renderer import CPURenderer, signature_instances

ROOT=Path(__file__).parents[1]
PATHS=sorted((ROOT/"templates").glob("00_v0833_*.json"))

def templates(): return [json.loads(p.read_text(encoding="utf-8")) for p in PATHS]
def state(n,time=4.0,onset=.62):
    x=np.linspace(0,1,n); values=np.clip(.18+.66*np.sin(x*4.7+1.1)**2,0,1).astype(np.float32)
    return {"values":values,"left_values":np.roll(values,1),"right_values":np.roll(values,-2)*.93,"bass":.76,"mid":.61,"high":.38,"onset":onset,"time":time}

def test_v0833_has_one_engine_and_three_personalities():
    ts=templates(); assert len(ts)==3
    assert {t["personality"] for t in ts}=={"DUAL","HIS","HER"}
    assert all(t["category"]=="signature_experimental_v3" and t["signature_variant"]=="tokyo_chill_signature" for t in ts)
    assert all(t["intensity"]=="DYNAMIC_SOFT" for t in ts)

def test_dynamic_soft_is_between_normal_and_dynamic():
    renderer=CPURenderer()
    for t in templates():
        s=state(t["bands"])
        heights=[]
        for mode in ("NORMAL","DYNAMIC_SOFT","DYNAMIC"):
            frame=renderer.render_rgba(960,160,s,dict(t,intensity=mode)); ys=np.where(frame[...,3]>20)[0]; heights.append(ys.max()-ys.min())
        assert heights[0] < heights[1] <= heights[2]

def test_continuous_center_and_balanced_stereo():
    for t in templates():
        frame=CPURenderer().render_rgba(960,160,state(t["bands"]),t); alpha=frame[...,3]
        assert alpha[:,460:500].max()>30
        left=np.count_nonzero(alpha[:,:480]>25);right=np.count_nonzero(alpha[:,480:]>25)
        assert .65 < left/max(1,right) < 1.45

def test_three_layers_and_temporal_color_motion():
    for t in templates():
        dots,lines=signature_instances(960,160,state(t["bands"],4),t)
        dots2,lines2=signature_instances(960,160,state(t["bands"],12),t)
        assert len(lines)>=3 and len(dots)>25
        assert [d[3] for d in dots[:12]] != [d[3] for d in dots2[:12]]
