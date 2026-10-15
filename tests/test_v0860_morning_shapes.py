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
        geometry=shape_geometry(1920,1080,state(),template);assert np.isfinite(geometry["points"]).all();assert np.max(np.abs(geometry["deformation"]))<=.095001


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
