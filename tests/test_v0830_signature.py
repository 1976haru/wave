import numpy as np
from pathlib import Path
from template_system import load_template
from render.renderer import CPURenderer, signature_instances
from render_job import resolve_template

FILES=sorted(Path("templates").glob("00_signature_*.json"))

def state(n,onset=.7):
    return {"values":np.resize(np.linspace(.08,.92,44,dtype=np.float32),n),"bass":.8,"mid":.55,"high":.2,"onset":onset,"time":1.25}

def test_signature_catalog_and_metadata():
    templates=[load_template(p) for p in FILES]
    assert len(templates)==6
    assert sum(t.get("signature_tier")=="MAIN" for t in templates)==3
    assert {t["renderer"] for t in templates}=={"dot_matrix","twin_dot_matrix","dot_line_hybrid","echo_dots"}
    assert all(t["canvas_profile"]["height"]==160 for t in templates)
    assert all(t["placement"]["safe_vertical_range"]==[45,65] for t in templates)
    assert resolve_template("CHILL_SIGNATURE_TWIN_SIGNAL")["name"]=="Twin Signal"

def test_signature_cpu_render_is_deterministic_and_black_outside_alpha():
    renderer=CPURenderer()
    for path in FILES:
        template=load_template(path); sample=state(template["bands"])
        a=renderer.render_rgba(960,160,sample,template); b=renderer.render_rgba(960,160,sample,template)
        assert np.array_equal(a,b)
        assert a[:,:,3].max()>0
        assert not np.any(a[:,:,:3][a[:,:,3]==0])

def test_main_three_have_distinct_grayscale_silhouettes():
    masks=[]
    for ident in ("TWIN_SIGNAL","MIDNIGHT_GRID","PETAL_PULSE"):
        path=next(p for p in FILES if ident.lower() in p.stem)
        template=load_template(path); frame=CPURenderer().render_rgba(960,160,state(template["bands"]),template)
        masks.append(frame[:,:,3]>32)
    for i,j in ((0,1),(0,2),(1,2)):
        intersection=np.logical_and(masks[i],masks[j]).sum(); union=np.logical_or(masks[i],masks[j]).sum()
        assert intersection/max(1,union)<.78

def test_twin_interaction_and_echo_are_onset_sensitive():
    for token in ("twin_signal","city_echo"):
        template=load_template(next(p for p in FILES if token in p.stem))
        low,_=signature_instances(960,160,state(template["bands"],0),template)
        high,_=signature_instances(960,160,state(template["bands"],1),template)
        assert len(high)>len(low) or any(abs(a[0]-b[0])>.01 for a,b in zip(low,high))
