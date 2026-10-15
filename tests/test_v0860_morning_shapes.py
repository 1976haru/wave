import copy
import json
from pathlib import Path

import numpy as np

from render.renderer import RendererFactory
from template_system import load_template
from visualizers.families.morning_shape import SHAPE_IDS, normalized_path, shape_geometry
from visualizers.schema import new_waveform
from visualizers.user_profiles import UserWaveformStore


ROOT = Path(__file__).resolve().parents[1]


def morning_templates():
    result=[]
    for path in (ROOT/"templates").glob("*.json"):
        data=load_template(path)
        if data.get("category")=="morning_chill_shapes":result.append((path,data))
    return result


def state():
    values=np.linspace(.12,.82,64,dtype=np.float32)
    return {"values":values,"left_values":values*.9,"right_values":values[::-1]*.8,"rms":.42,"bass":.55,"mid":.38,"high":.24,"onset":.12}


def test_exactly_100_templates_and_20_morning_shapes():
    assert len(list((ROOT/"templates").glob("*.json")))==100
    templates=morning_templates();assert len(templates)==20
    assert {data["id"] for _,data in templates}==set(SHAPE_IDS)


def test_geometry_is_finite_continuous_and_bounded():
    for sid in SHAPE_IDS:
        path=normalized_path(sid,240);assert path.shape==(240,2);assert np.isfinite(path).all()
        if sid!="SUNRISE_ARC":assert np.linalg.norm(path[0]-path[-1])<.2
        template={"_quality":"QUALITY","morning_shape":{"shape_id":sid,"movement":"LIVELY","shape_size":1.0,"response_strength":2.0}}
        geometry=shape_geometry(1920,1080,state(),template);assert np.isfinite(geometry["points"]).all();assert np.max(np.abs(geometry["deformation"]))<=.080001


def test_exact_circle_oval_ratios_radial_normals_and_clean_center():
    for sid in ("MORNING_HALO","PEARL_HALO","TWIN_HALO","BREATHING_RING","FLOWER_HALO"):
        g=shape_geometry(1920,1080,state(),{"morning_shape":{"shape_id":sid}});span=np.ptp(g["base_points"],axis=0)
        if sid!="FLOWER_HALO":assert abs(float(span[0]/span[1])-1)<.015
        radial=g["base_points"]-g["profile"]["center"];assert np.mean(np.sum(radial*g["normals"],axis=1))>0
        assert np.min(np.linalg.norm(g["points"]-g["profile"]["center"],axis=1))>150
    soft=normalized_path("SOFT_OVAL",240);vertical=normalized_path("VERTICAL_OVAL",240)
    assert 1.45<np.ptp(soft[:,0])/np.ptp(soft[:,1])<1.7
    assert 1.35<np.ptp(vertical[:,1])/np.ptp(vertical[:,0])<1.55


def test_morning_frame_has_no_legacy_bottom_equalizer():
    template=load_template(ROOT/"templates/60_morning_halo.json");frame=RendererFactory.create("CPU",template).render_rgba(960,540,state(),template)
    assert not np.any(frame[int(540*.78):,:,3])
    center=frame[220:320,430:530,3];assert center.max()==0


def test_shape_specific_geometry_is_distinct():
    signatures=[]
    for sid in SHAPE_IDS:
        path=normalized_path(sid,240);radius=np.linalg.norm(path,axis=1);signatures.append(np.round(np.r_[np.ptp(path,axis=0),np.percentile(radius,[10,35,60,90])],3))
    # Parametric families may share broad extents, but every named group must
    # retain a visibly distinct radial/extent signature.
    assert len({tuple(row) for row in signatures})>=12
    contour_ids=("SOFT_OVAL","VERTICAL_OVAL","ROUND_SQUARE","SOFT_DIAMOND","HEART_WHISPER","SOFT_CAPSULE","CLOUD_LOOP","PETAL_LOOP","FLOWER_HALO","CAFE_FRAME")
    contour_signatures=[]
    for sid in contour_ids:
        path=normalized_path(sid,240);radius=np.linalg.norm(path,axis=1);contour_signatures.append(tuple(np.round(np.r_[np.ptp(path,axis=0),np.percentile(radius,[10,35,60,90])],3)))
    assert len(set(contour_signatures))==len(contour_ids)


def test_sizes_colors_gradient_opacity_position_and_render_parity():
    base=load_template(ROOT/"templates/60_morning_halo.json")
    for size in (.5,1,1.5,2):
        template=copy.deepcopy(base);template["morning_shape"].update(shape_size=size,color_mode="GRADIENT",color_a="#123456",color_b="#FEDCBA",opacity=.4,position_x=.25,position_y=.7,movement="STANDARD",stroke_style="THICK",glow_level="DEFAULT")
        a=RendererFactory.create("CPU",template).render_rgba(640,360,state(),template)
        b=RendererFactory.create("AUTO",template).render_rgba(640,360,state(),dict(template,_quality="BALANCED"))
        assert a.shape==b.shape==(360,640,4);assert np.array_equal(a,b);assert a[:,:,3].max()>0


def test_mwswave_roundtrip_backward_compatible(tmp_path):
    settings=copy.deepcopy(load_template(ROOT/"templates/61_pearl_halo.json")["morning_shape"])
    waveform=new_waveform("Pearl",renderer_family="morning_shape",theme="WARM",intensity="CALM",width="STANDARD",position="CENTER",color_mode="CUSTOM",colors=[settings["color_a"],settings["color_b"]],morning_shape=settings)
    store=UserWaveformStore(tmp_path);saved=store.save(waveform);loaded=store.load(saved)
    assert loaded["renderer_family"]=="morning_shape";assert loaded["morning_shape"]==settings
    legacy=new_waveform("Legacy");assert store.save(legacy).exists()
