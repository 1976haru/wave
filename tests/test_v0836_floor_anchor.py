from pathlib import Path
import json
import numpy as np
from render.renderer import signature_instances

ROOT=Path(__file__).parents[1]
PATHS=sorted((ROOT/"templates").glob("00_v0834_tokyo_chill_*.json"))

def templates():
    return [json.loads(path.read_text(encoding="utf-8")) for path in PATHS]

def state_for(template,level,onset=0.0,time=0.0):
    n=int(template["bands"])
    values=np.linspace(level*.75,level,n,dtype=np.float32)
    return {
        "values":values,
        "left_values":np.roll(values,1)*.97,
        "right_values":np.roll(values,-2)*1.02,
        "bass":level,
        "mid":level*.85,
        "high":level*.60,
        "onset":onset,
        "time":time,
    }

def geometry(template,level,onset=0.0,time=0.0):
    dots,lines=signature_instances(960,160,state_for(template,level,onset,time),template)
    base=160*float(template.get("anchor_y",template.get("baseline_y",.82)))
    dot_y=np.asarray([d[1] for d in dots],dtype=np.float32)
    line_y=np.concatenate([np.asarray(layer["points"])[:,1] for layer in lines])
    return base,dots,lines,dot_y,line_y

def test_floor_anchor_is_fixed_and_nothing_moves_below_it():
    for template in templates():
        for level,onset in ((.18,0.0),(.48,.25),(.86,.80)):
            base,dots,lines,dot_y,line_y=geometry(template,level,onset,7.3)
            assert len(dots)>30 and len(lines)>=4
            assert np.max(dot_y)<=base+.05
            assert np.max(line_y)<=base+.05
            assert np.any(np.isclose(dot_y,base,atol=.05))
            assert np.any(np.isclose(line_y,base,atol=.05))

def test_strong_music_expands_upward_by_at_least_45_pixels():
    for template in templates():
        base,_,_,low_y,_=geometry(template,.18,0.0,2.0)
        _,_,_,high_y,_=geometry(template,.86,.80,2.0)
        low_height=base-float(np.min(low_y))
        high_height=base-float(np.min(high_y))
        assert high_height>=low_height+45.0
        assert high_height>=85.0

def test_colour_changes_with_energy_and_time():
    for template in templates():
        _,low,_,_,_=geometry(template,.22,.0,1.0)
        _,high,_,_,_=geometry(template,.82,.75,1.0)
        _,later,_,_,_=geometry(template,.82,.75,5.5)
        low_colors={d[3] for d in low}
        high_colors={d[3] for d in high}
        later_colors={d[3] for d in later}
        assert low_colors!=high_colors
        assert high_colors!=later_colors

def test_final_templates_use_floor_anchor_parameters():
    for template in templates():
        assert template["version"]=="0.8.3.6"
        assert .80<=float(template["anchor_y"])<=.84
        assert float(template["baseline_y"])==float(template["anchor_y"])
        assert template["adaptive_normalization"] is True
        assert float(template["adaptive_blend"])>=.68
        assert float(template["color_flow_seconds"])<=10.0
