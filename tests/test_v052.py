import json
from pathlib import Path
import cv2,numpy as np,pytest
from preview.engine import PreviewEngine
from preview.scheduler import FrameScheduler
from render.renderer import AutoRenderer,CPURenderer,build_line_vertices
from template_system import DEFAULT_TEMPLATE
from tools.export_smoke import validate_probe
from tools.system_check import parse_encoders
from tools.update_visual_baselines import CASES,render_case
from ui.roi_widget import ImageTransform,ROISelectionModel

def test_roi_letterbox_coordinate_mapping():
    transform=ImageTransform(800,600,1920,1080);assert transform.content_rect==(0.0,75.0,800.0,450.0);assert transform.widget_to_image(400,300)==(960,540)
def test_roi_clamps_outside_image():
    transform=ImageTransform(800,600,1920,1080);assert transform.widget_to_image(-20,0)==(0,0) and transform.widget_to_image(900,700)==(1920,1080)
def test_roi_rectangle_maps_to_original():
    from PySide6.QtCore import QRect
    roi=ImageTransform(800,600,1920,1080).rect_to_image(QRect(200,188,400,224));assert abs(roi[0]-480)<=2 and abs(roi[1]-271)<=2 and abs(roi[2]-960)<=3
def test_roi_drag_state_normalizes_reverse_drag():
    model=ROISelectionModel();model.press(100,80);model.move(20,10);model.release(20,10);rect=model.rectangle;assert (rect.left(),rect.top(),rect.right(),rect.bottom())==(20,10,100,80) and not model.active
def test_roi_reset():
    model=ROISelectionModel();model.press(1,2);model.release(4,6);model.reset();assert model.rectangle is None
def test_scheduler_drops_late_frames():
    scheduler=FrameScheduler(24);scheduler.reset(0,0);assert scheduler.should_render(0,0);assert scheduler.should_render(.2,.2);assert scheduler.metrics.dropped_frames>=3
def test_scheduler_does_not_queue_early_frame():
    scheduler=FrameScheduler(24);scheduler.reset(0,0);assert scheduler.should_render(0,0);assert not scheduler.should_render(.01,.01)
def test_scheduler_seek_resets_drop_state():
    scheduler=FrameScheduler(24);scheduler.reset(1,0);scheduler.should_render(2,1);scheduler.seek(.5,2);assert scheduler.metrics.dropped_frames==0 and scheduler.should_render(.5,2)
def test_scheduler_backward_audio_resets():
    scheduler=FrameScheduler(24);scheduler.reset(2,0);scheduler.should_render(2,0);scheduler.should_render(1,1);assert scheduler.metrics.dropped_frames==0
def test_preview_seek_resets_animation():
    features={"spectrum":np.ones((2,4),np.float32),"rms":np.ones(2),"bass":np.ones(2),"mid":np.ones(2),"high":np.ones(2),"onset":np.zeros(2),"fps":np.array([24]),"duration":np.array([1])};engine=PreviewEngine(80,40);engine.features=features;engine.template=dict(DEFAULT_TEMPLATE,bands=4);from animation.engine import AnimationEngine;engine.animation=AnimationEngine(features,engine.template);engine.seek(.5);assert engine.last_time==.5 and engine.animation.prev is None
def test_gpu_line_vertices_are_connected_strip():
    values=np.array([.1,.9,.2,.8],np.float32);vertices=build_line_vertices(320,180,values,dict(DEFAULT_TEMPLATE,renderer="line"));assert vertices.shape==(8,5) and np.all(np.isfinite(vertices))
def test_gpu_line_mirror_changes_vertical_geometry():
    values=np.array([.2,.7,.4],np.float32);normal=build_line_vertices(320,180,values,DEFAULT_TEMPLATE);mirror=build_line_vertices(320,180,values,DEFAULT_TEMPLATE,True);assert not np.allclose(normal[:,1],mirror[:,1])
def test_auto_renderer_runtime_gpu_failure():
    auto=AutoRenderer()
    class Broken:
        def render_rgba(self,*_):raise RuntimeError("shader failed")
    auto.active=Broken();image=auto.render_rgba(80,40,{"values":np.ones(4)},dict(DEFAULT_TEMPLATE,glow=False));assert auto.name=="CPU" and image.shape==(40,80,4)
def test_cpu_glow_expands_alpha_area():
    renderer=CPURenderer();state={"values":np.array([0,0,1,0,0],np.float32)};plain=renderer.render_rgba(160,90,state,dict(DEFAULT_TEMPLATE,glow=False));glow=renderer.render_rgba(160,90,state,dict(DEFAULT_TEMPLATE,glow=True,glow_radius=8));assert np.count_nonzero(glow[:,:,3])>np.count_nonzero(plain[:,:,3])
def test_encoder_parser():
    text=" V..... libx264 H.264\n V..... libvpx-vp9 VP9\n V..... prores_ks ProRes";assert parse_encoders(text)=={"libx264","libvpx-vp9","prores_ks"}
def test_ffprobe_validation_metadata():
    data={"format":{"duration":"1.02"},"streams":[{"codec_type":"video","width":320,"height":180,"r_frame_rate":"24/1","pix_fmt":"yuva420p"},{"codec_type":"audio","duration":"1.0"}]};result=validate_probe(data,320,180,24,1);assert result["duration_within_one_frame"] and result["alpha_present"] and result["audio_present"]
@pytest.mark.parametrize("case",sorted(CASES))
def test_cpu_visual_regression(case):
    baseline=cv2.imread(str(Path("tests/baselines")/f"{case}.png"),cv2.IMREAD_UNCHANGED);actual=render_case(CASES[case]);baseline=cv2.cvtColor(baseline,cv2.COLOR_BGRA2RGBA);difference=np.mean(np.abs(actual.astype(np.float32)-baseline.astype(np.float32)))/255;assert difference<.03

def test_preview_long_session_policy():
    from tools.validate_preview import simulate
    report=simulate(60);assert report["average_fps"]>=23.5 and report["max_drift_ms"]<=1000/24 and report["drop_ratio"]<.02

def test_system_check_has_required_sections():
    from tools.system_check import check_system
    report=check_system();assert {"python","ffmpeg","ffprobe","PySide6","NumPy","OpenCV","H.264","VP9","ProRes"}<=set(report)

def test_gpu_cpu_visual_similarity_when_available():
    from render.renderer import GPUBarRenderer
    try:gpu=GPUBarRenderer()
    except Exception:pytest.skip("ModernGL context unavailable")
    template=dict(DEFAULT_TEMPLATE,renderer="line",gradient=True,mirror=True,glow=False,bands=32);state={"values":np.linspace(.1,.9,32,dtype=np.float32)};cpu=CPURenderer().render_rgba(320,180,state,template);actual=gpu.render_rgba(320,180,state,template);difference=np.mean(np.abs(cpu.astype(np.float32)-actual.astype(np.float32)))/255;assert difference<.25