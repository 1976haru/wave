import json
from pathlib import Path
import numpy as np
from animation.engine import AnimationEngine
from render_job import resolve_template

ROOT=Path(__file__).parents[1]
T=json.loads((ROOT/"templates/00_v0834_tokyo_chill_his.json").read_text(encoding="utf-8"))

def features(frames=240,bands=51):
    time=np.linspace(0,8,frames,dtype=np.float32);base=np.linspace(.002,.08,bands,dtype=np.float32)
    spectrum=np.asarray([base*(.3+.7*np.sin(t*1.7)**2) for t in time],np.float32)
    signal=np.clip(.12+.5*np.sin(time*.8)**2,0,1).astype(np.float32)
    return {"spectrum":spectrum,"rms":signal,"bass":signal,"mid":signal*.8,"high":signal*.4,"onset":np.maximum(0,np.sin(time*3))*.3,"fps":np.array([24]),"duration":np.array([10.])}

def test_stable_id_and_display_name_resolve_to_final():
    assert resolve_template("TOKYO_CHILL_HIS")["id"]=="TOKYO_CHILL_HIS"
    assert resolve_template("Tokyo Midnight Flow")["id"]=="TOKYO_CHILL_HIS"

def test_robust_calibration_expands_narrow_real_music_proxy():
    f=features();before=AnimationEngine(f,dict(T,signature_tier="EXPERIMENTAL"));after=AnimationEngine(f,T)
    old=np.asarray([np.median(before.sample(i/24)["values"]) for i in range(240)])
    new=np.asarray([np.median(after.sample(i/24)["values"]) for i in range(240)])
    assert np.percentile(new,90)-np.percentile(new,10)>np.percentile(old,90)-np.percentile(old,10)
    assert new.min()>=float(T.get("signature_body_floor",.12))

def test_absolute_time_is_separate_from_track_time():
    state=AnimationEngine(features(),T).sample(1.25,absolute_seconds=361.25)
    assert state["time"]==361.25 and state["track_time"]==1.25
