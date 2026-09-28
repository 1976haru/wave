from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from template_system import load_template
from visualizers.families.tokyo_signature import RECOMMENDED, TokyoSignatureRenderer, resolve_signature_profile, signature_geometry
from visualizers.registry import registry
from visualizers.schema import new_waveform, validate_waveform
from visualizers.user_profiles import UserWaveformStore

FILES=sorted(Path("templates").glob("00_v0850_tokyo_*.json"))


def state(level=.55,onset=.3):
    values=np.clip(level*(.58+.42*np.abs(np.sin(np.linspace(0,8,64)))),0,1).astype(np.float32)
    return {"values":values,"left_values":np.roll(values,1),"right_values":np.roll(values,-2),"bass":level,"mid":level*.9,"high":level*.7,"energy":level,"onset":onset,"auto_gain":1.0,"time":3.0}


def test_three_signatures_load_and_registry():
    assert len(FILES)==3 and "tokyo_signature" in registry.ids()
    assert {load_template(p)["id"] for p in FILES}=={"TOKYO_MIDNIGHT_PULSE","TOKYO_SILK_WAVE","TOKYO_TWO_HEARTS"}


def test_render_bounds_finite_and_distinct_geometry():
    masks=[]
    for path in FILES:
        template=load_template(path);image=TokyoSignatureRenderer().render_rgba(960,160,state(),template)
        assert image.shape==(160,960,4) and np.isfinite(image).all() and image[...,3].max()>0
        ys,xs=np.where(image[...,3]>12);assert xs.min()>=0 and xs.max()<960 and ys.min()>=0 and ys.max()<160;masks.append(image[...,3]>18)
    overlaps=[]
    for i in range(3):
        for j in range(i+1,3):overlaps.append(np.logical_and(masks[i],masks[j]).sum()/max(1,np.logical_or(masks[i],masks[j]).sum()))
    assert max(overlaps)<.72


def test_four_motion_levels_increase_vertical_range():
    for path in FILES:
        template=load_template(path);rises=[]
        for motion in ("CALM","STANDARD","DYNAMIC","VERY_DYNAMIC"):
            candidate=copy.deepcopy(template);candidate["tokyo_signature"]["motion"]=motion;geo=signature_geometry(960,160,state(.72,.65),candidate);ys=[d[1] for d in geo["dots"]]+[float(p[1]) for line in geo["lines"] for p in line[0]]+[b[1]-b[2] for b in geo["bars"]];rises.append(geo["profile"]["base"]-min(ys))
        assert all(right>left for left,right in zip(rises,rises[1:])),rises


def test_size_position_presence_and_recommended_contract():
    for path in FILES:
        template=load_template(path);variant=template["tokyo_signature"]["variant"]
        assert all(key in RECOMMENDED[variant] for key in ("motion","size","vertical_position","presence"))
        small=copy.deepcopy(template);small["tokyo_signature"]["size"]=.7
        large=copy.deepcopy(template);large["tokyo_signature"]["size"]=1.3
        assert resolve_signature_profile(small,960,160)["active_width"]<resolve_signature_profile(large,960,160)["active_width"]
        top=copy.deepcopy(template);top["tokyo_signature"]["vertical_position"]="TOP"
        bottom=copy.deepcopy(template);bottom["tokyo_signature"]["vertical_position"]="BOTTOM"
        assert resolve_signature_profile(top,960,160)["base"]<resolve_signature_profile(bottom,960,160)["base"]


def test_local_background_adapt_and_preview_render_determinism():
    template=load_template(FILES[0]);sample=state();sample["background_frame"]=np.full((160,960,3),245,np.uint8)
    renderer=TokyoSignatureRenderer();first=renderer.render_rgba(960,160,sample,template);second=TokyoSignatureRenderer().render_rgba(960,160,sample,template)
    assert np.array_equal(first,second) and renderer.last_local_metrics is not None


def test_mwswave_signature_roundtrip_and_old_compatibility():
    waveform=new_waveform("Tokyo Test",renderer_family="tokyo_signature",position="LEFT",signature={"variant":"TWO_HEARTS","motion":"VERY_DYNAMIC","size":1.1,"vertical_position":"BOTTOM","horizontal_position":"LEFT","presence":"CRISP","auto_adapt":True,"local_adapt":True,"colors":[]})
    clean,warnings=validate_waveform(waveform,{"soft_round_led","tokyo_signature"});assert clean["signature"]["variant"]=="TWO_HEARTS" and not warnings
    old=new_waveform("Old Universal");assert old["renderer_family"]=="soft_round_led" and "signature" not in old


def test_signature_my_waveform_save_reload():
    store=UserWaveformStore("validation_results/tokyo_signature_v1/_waveform_store",{"soft_round_led","tokyo_signature"})
    waveform=new_waveform("Tokyo Signature Test",renderer_family="tokyo_signature",position="CENTER",signature={"variant":"SILK_WAVE","motion":"DYNAMIC","size":1.08,"vertical_position":"CENTER","horizontal_position":"CENTER","presence":"DEFAULT","auto_adapt":True,"local_adapt":True,"colors":[]})
    path=store.save(waveform,overwrite=True);loaded=store.load(path);assert loaded["signature"]==waveform["signature"] and loaded["renderer_family"]=="tokyo_signature"
