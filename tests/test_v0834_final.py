from pathlib import Path
import json
from core.version import get_version
from render.renderer import signature_instances
import numpy as np

ROOT=Path(__file__).parents[1]
PATHS=sorted((ROOT/"templates").glob("00_v0834_*.json"))
def load():return [json.loads(p.read_text(encoding="utf-8")) for p in PATHS]

def test_final_ids_and_defaults():
    items=load();assert len(items)==3
    assert {x["id"] for x in items}=={"TOKYO_CHILL_DUAL","TOKYO_CHILL_HIS","TOKYO_CHILL_HER"}
    assert all(x["signature_tier"]=="FINAL" and x["intensity"]=="DYNAMIC_SOFT" for x in items)
    assert all(x["canvas_profile"]=={"width":960,"height":160,"fps":24,"pixel_format":"yuv420p","codec":"H.264","crf":18,"background":"#000000"} for x in items)

def test_final_polish_parameters():
    by_id={x["id"]:x for x in load()}
    assert 1.05<=by_id["TOKYO_CHILL_DUAL"]["lower_response_gain"]<=1.10
    assert 1.05<=by_id["TOKYO_CHILL_DUAL"]["center_bridge_gain"]<=1.10
    assert .075<by_id["TOKYO_CHILL_HIS"]["halo_alpha"]<.09
    assert .55<=by_id["TOKYO_CHILL_HER"]["lower_ribbon_alpha"]<=.61
    assert by_id["TOKYO_CHILL_HER"]["placement"]["vertical_percent"]==59

def test_final_geometry_has_center_continuity():
    for t in load():
        n=t["bands"];v=np.linspace(.2,.8,n,dtype=np.float32);state={"values":v,"left_values":np.roll(v,1),"right_values":np.roll(v,-2),"bass":.7,"mid":.6,"high":.3,"onset":.5,"time":8}
        dots,lines=signature_instances(960,160,state,t);assert len(lines)>=3 and len(dots)>20
        assert any(np.any((layer["points"][:,0]>450)&(layer["points"][:,0]<510)) for layer in lines)

def test_version():assert get_version() in {"0.8.3.4","0.8.3.5"}
