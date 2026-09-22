import json
from pathlib import Path
import cv2,numpy as np,pytest
from animation.engine import AnimationEngine
from pipeline.batch import BatchRunner
from pipeline.exporter import ExportOptions,build_ffmpeg_command,output_extension
from preview.engine import PreviewEngine,format_time
from reference.analyzer import analyze_images,analyze_video
from render.renderer import CPURenderer,gradient_colors
from template_system import DEFAULT_TEMPLATE,list_templates,load_template,save_template

def state(values=(.2,.5,.8,1)):return {"values":np.asarray(values,np.float32)}
def render(style="bars",**changes):
    template=dict(DEFAULT_TEMPLATE,renderer=style,glow=False,**changes);return CPURenderer().render_rgba(240,120,state(),template)

def test_gradient_interpolates_colors():
    colors=gradient_colors({"gradient":True,"gradient_start":"#FF0000","gradient_end":"#0000FF"},3)
    assert tuple(colors[0])==(255,0,0) and tuple(colors[-1])==(0,0,255)
def test_cpu_bars_gradient_output():
    image=render(gradient=True,gradient_start="#FF0000",gradient_end="#0000FF")
    pixels=image[image[:,:,3]>200,:3];assert pixels[:,0].max()>200 and pixels[:,2].max()>200
def test_cpu_line_output():assert render("line")[:,:,3].max()>0
def test_cpu_dot_output():assert render("dot")[:,:,3].max()>0
def test_cpu_mirror_draws_both_sides():
    image=render("bars",mirror=True,position="center");alpha=image[:,:,3];assert alpha[:60].sum()>0 and alpha[61:].sum()>0
def test_opacity_is_true_alpha():assert 120<=render(opacity=.5)[:,:,3].max()<=130
def test_gallery_contains_eight_presets():
    items=list_templates("templates");names={data["name"] for _,data in items};assert len(names)>=8 and "01 Clean Bars" in names and "08 Elegant White" in names
def test_my_template_save_and_listing(tmp_path):
    save_template(tmp_path/"mine.json",dict(DEFAULT_TEMPLATE,name="Mine",renderer="dot"));items=list_templates(tmp_path);assert len(items)==1 and items[0][1]["renderer"]=="dot"
def test_format_time():assert format_time(13)=="00:13" and format_time(272)=="04:32"
def test_preview_frame_without_fft_recalculation():
    features={"spectrum":np.ones((4,8),np.float32)*.5,"rms":np.ones(4),"bass":np.ones(4),"mid":np.ones(4),"high":np.ones(4),"onset":np.zeros(4),"fps":np.array([24]),"duration":np.array([1.0])};engine=PreviewEngine(240,120);engine.features=features;engine.template=dict(DEFAULT_TEMPLATE,bands=8,glow=False);engine.renderer=CPURenderer();engine.animation=AnimationEngine(features,engine.template);frame=engine.frame(.1);assert frame.shape==(120,240,4) and engine.metrics.fps>0
def test_preview_detects_band_change():
    engine=PreviewEngine();engine.features={"duration":np.array([1]),"spectrum":np.ones((2,32),np.float32),"fps":np.array([24]),"rms":np.ones(2),"bass":np.ones(2),"mid":np.ones(2),"high":np.ones(2),"onset":np.zeros(2)};engine.template={"bands":32};assert engine.update_template({"bands":64}) and engine.features["spectrum"].shape[1]==64
def test_export_options_and_extensions():
    option=ExportOptions.from_resolution("1080x1920",fps=60,format="webm");assert (option.width,option.height,option.fps)==(1080,1920,60) and output_extension("webm")==".webm"
@pytest.mark.parametrize("suffix,codec",[(".mp4","libx264"),(".webm","libvpx-vp9"),(".mov","prores_ks")])
def test_export_command_formats(tmp_path,suffix,codec):
    option=ExportOptions(format=suffix[1:]);command=build_ffmpeg_command("ffmpeg",tmp_path/f"out{suffix}",option,"song.wav");assert codec in command and "-shortest" in command
def test_reference_image_analysis(tmp_path):
    image=np.zeros((120,240,3),np.uint8)
    for x in range(30,210,20):cv2.rectangle(image,(x,45),(x+7,100),(20,180,240),-1)
    path=tmp_path/"ref.png";cv2.imwrite(str(path),image);result=analyze_images([path]);assert result["bands"]>=8 and result["color"].startswith("#") and 0<result["gap"]<1
def test_reference_roi_validation(tmp_path):
    path=tmp_path/"ref.png";cv2.imwrite(str(path),np.zeros((20,20,3),np.uint8))
    with pytest.raises(ValueError):analyze_images([path],(15,15,20,20))
def test_reference_video_motion_mapping(monkeypatch):
    frames=[np.full((60,100,3),i*20,np.uint8) for i in range(8)]
    class Capture:
        def __init__(self,*_):self.i=0
        def get(self,*_):return 10
        def read(self):
            if self.i>=len(frames):return False,None
            value=frames[self.i];self.i+=1;return True,value
        def release(self):pass
    monkeypatch.setattr(cv2,"VideoCapture",Capture);result=analyze_video("fake.mp4",max_seconds=5);assert 0<=result["motion_speed"]<=1 and .12<=result["attack"]<=.7 and .68<=result["decay"]<=.96
def test_fifteen_song_queue_simulation(tmp_path):
    files=[f"song{i}.wav" for i in range(15)];results=BatchRunner().run(files,tmp_path,{},render_fn=lambda *a,**k:{})
    assert len(results)==15 and all(item["status"]=="success" for item in results)
def test_gui_module_import():
    import ui.main_window
    assert hasattr(ui.main_window,"MainWindow")

def test_renderer_consistency_factory_cpu():
    from render.renderer import RendererFactory
    expected=render("bars",gradient=True,gradient_start="#112233",gradient_end="#445566",mirror=True)
    actual=RendererFactory.create("CPU").render_rgba(240,120,state(),dict(DEFAULT_TEMPLATE,renderer="bars",gradient=True,gradient_start="#112233",gradient_end="#445566",mirror=True,glow=False))
    assert np.array_equal(expected,actual)