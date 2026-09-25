from pathlib import Path
import numpy as np
from template_system import load_template
from render.renderer import CPURenderer,signature_instances
from render_job import resolve_template

FILES=sorted(Path("templates").glob("00_v0832_*.json"))

def state(n,onset=.75,time=2.0):
    values=np.resize(np.array([.22,.35,.58,.82,.45,.70,.32,.91],np.float32),n)
    return {"values":values,"left_values":np.roll(values,1),"right_values":np.roll(values,-2),"bass":.84,"mid":.62,"high":.30,"onset":onset,"left_onset":onset*.9,"right_onset":onset*.78,"time":time}

def test_only_three_v2_experimental_presets_exist():
    templates=[load_template(p) for p in FILES]
    assert len(templates)==3
    assert {t["signature_variant"] for t in templates}=={"twin_bloom_v2","midnight_grid_v2","pearl_bloom_v2"}
    assert all(t["category"]=="signature_experimental_v2" and t["intensity"]=="NORMAL" for t in templates)
    assert resolve_template("CHILL_V0832_TWIN_BLOOM_V2")["canvas_profile"]=={"width":960,"height":160,"fps":24,"pixel_format":"yuv420p"}

def test_v2_is_tall_bidirectional_and_dynamic_is_larger():
    renderer=CPURenderer()
    for path in FILES:
        t=load_template(path);s=state(t["bands"]);normal=renderer.render_rgba(960,160,s,dict(t,intensity="NORMAL"));dynamic=renderer.render_rgba(960,160,s,dict(t,intensity="DYNAMIC"))
        def height(frame):
            y=np.where(frame[:,:,3]>28)[0];return int(y.max()-y.min()+1)
        assert height(normal)>=35
        assert height(dynamic)>height(normal)
        mask=dynamic[:,:,3]>28;left=mask[:,:480].sum();right=mask[:,480:].sum();assert min(left,right)/max(left,right)>.72

def test_layers_color_flow_and_center_onset_are_real():
    for path in FILES:
        t=load_template(path);dots,lines=signature_instances(960,160,state(t["bands"],time=1),dict(t,intensity="DYNAMIC"));dots2,lines2=signature_instances(960,160,state(t["bands"],time=8),dict(t,intensity="DYNAMIC"))
        assert len(lines)>=2
        colors={d[3] for d in dots}|{layer["color"] for layer in lines};assert len(colors)>=3
        sequence=[d[3] for d in dots]+[layer["color"] for layer in lines];sequence2=[d[3] for d in dots2]+[layer["color"] for layer in lines2];assert sequence!=sequence2
    twin=load_template(next(p for p in FILES if "twin" in p.stem));quiet,_=signature_instances(960,160,state(twin["bands"],0),twin);strong,_=signature_instances(960,160,state(twin["bands"],1),twin);assert len(strong)>len(quiet)
