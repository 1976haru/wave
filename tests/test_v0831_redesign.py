from pathlib import Path
import numpy as np
from template_system import load_template
from render.renderer import CPURenderer,signature_instances

FILES=sorted(Path("templates").glob("00_v0831_*.json"))

def state(n,time=1.2):
    return {"values":np.resize(np.linspace(.12,.92,50,dtype=np.float32),n),"bass":.82,"mid":.57,"high":.24,"onset":.68,"time":time}

def test_nine_candidates_three_per_story_and_three_recommended():
    templates=[load_template(p) for p in FILES]
    assert len(templates)==9
    assert {c:sum(t["signature_category"]==c for t in templates) for c in ("Dual","His","Her")}=={"Dual":3,"His":3,"Her":3}
    assert sum(bool(t.get("recommended")) for t in templates)==3
    assert all(t["renderer"]=="stereo_signature" for t in templates)

def test_all_candidates_are_bidirectional_and_deterministic():
    renderer=CPURenderer()
    for path in FILES:
        template=load_template(path);sample=state(template["bands"]);a=renderer.render_rgba(960,160,sample,template);b=renderer.render_rgba(960,160,sample,template)
        assert np.array_equal(a,b)
        mask=a[:,:,3]>28;left=mask[:,:480].sum();right=mask[:,480:].sum()
        assert min(left,right)/max(left,right)>.70

def test_variants_have_distinct_silhouettes():
    masks=[]
    for path in FILES:
        template=load_template(path);frame=CPURenderer().render_rgba(960,160,state(template["bands"]),template);masks.append(frame[:,:,3]>28)
    assert max(np.logical_and(a,b).sum()/max(1,np.logical_or(a,b).sum()) for i,a in enumerate(masks) for b in masks[i+1:])<.80

def test_motion_is_time_deterministic_not_random():
    template=load_template(next(p for p in FILES if "silk_ribbon" in p.stem));sample=state(template["bands"])
    _,a=signature_instances(960,160,sample,template);_,b=signature_instances(960,160,state(template["bands"],2.0),template)
    assert not np.array_equal(a[0]["points"],b[0]["points"])
