import json,threading
from pathlib import Path
import numpy as np,pytest
from pipeline.batch import BatchRunner
from pipeline.exporter import ExportOptions,build_ffmpeg_command
from preview.worker import LatestFrameMailbox
from render.quality import PRESETS
from render.renderer import CPURenderer,gradient_colors
from template_system import DEFAULT_TEMPLATE

def test_latest_mailbox_replaces_pending_request():
    mailbox=LatestFrameMailbox();mailbox.submit(1,{"name":"old"});latest=mailbox.submit(2,{"name":"new"});request=mailbox.take();assert request.sequence==latest and request.seconds==2 and request.template["name"]=="new" and mailbox.replaced==1
def test_latest_mailbox_take_clears_slot():
    mailbox=LatestFrameMailbox();mailbox.submit(1,{});assert mailbox.take() is not None and mailbox.take() is None
def test_latest_mailbox_thread_safety():
    mailbox=LatestFrameMailbox();threads=[threading.Thread(target=lambda start=i:[mailbox.submit(start+j,{}) for j in range(50)]) for i in range(4)]
    [thread.start() for thread in threads];[thread.join() for thread in threads];assert mailbox.take().sequence==200 and mailbox.replaced==199
def test_batch_state_persists_completed(tmp_path):
    runner=BatchRunner();runner.run(["one.wav"],tmp_path,{},render_fn=lambda *a,**k:{"frames":2});state=json.loads((tmp_path/"batch_state.json").read_text());entry=next(iter(state["tracks"].values()));assert entry["status"]=="completed" and entry["attempts"]==1
def test_batch_skip_completed_output(tmp_path):
    source="one.wav";target=tmp_path/"one.mp4";target.write_bytes(b"done");key=str(Path(source).resolve());state={"version":1,"tracks":{key:{"file":source,"output":str(target),"status":"completed","attempts":1}}};(tmp_path/"batch_state.json").write_text(json.dumps(state));called=[];result=BatchRunner().run([source],tmp_path,{},render_fn=lambda *a,**k:called.append(1),skip_completed=True);assert result[0]["status"]=="skipped" and not called
def test_batch_recovers_rendering_state(tmp_path):
    source="resume.wav";target=tmp_path/"resume.mp4";key=str(Path(source).resolve());state={"version":1,"tracks":{key:{"file":source,"output":str(target),"status":"rendering","attempts":1}}};(tmp_path/"batch_state.json").write_text(json.dumps(state));BatchRunner().run([source],tmp_path,{},render_fn=lambda *a,**k:{});saved=json.loads((tmp_path/"batch_state.json").read_text());assert saved["tracks"][key]["status"]=="completed" and saved["tracks"][key]["attempts"]==2
def test_batch_state_atomic_temp_removed(tmp_path):
    BatchRunner().run(["one.wav"],tmp_path,{},render_fn=lambda *a,**k:{});assert not (tmp_path/"batch_state.tmp").exists()
@pytest.mark.parametrize("quality,glow",[("PREVIEW",.25),("BALANCED",.5),("QUALITY",1.0)])
def test_quality_glow_profiles(quality,glow):assert PRESETS[quality]["glow_scale"]==glow
def test_quality_crf_order():assert PRESETS["PREVIEW"]["crf"]>PRESETS["BALANCED"]["crf"]>PRESETS["QUALITY"]["crf"]
def test_quality_does_not_change_requested_resolution():
    option=ExportOptions(1080,1920,60,"QUALITY");assert (option.width,option.height,option.fps)==(1080,1920,60)
def test_mp4_command_uses_quality_encoder_preset(tmp_path):
    command=build_ffmpeg_command("ffmpeg",tmp_path/"x.mp4",ExportOptions(320,180,24,"PREVIEW"),"x.wav");assert command[command.index("-preset")+1]=="veryfast"
def test_gradient_lut_is_reused():
    template=dict(DEFAULT_TEMPLATE,gradient=True);assert gradient_colors(template,32) is gradient_colors(template,32)
def test_cpu_renderer_exposes_stage_profile():
    renderer=CPURenderer();renderer.render_rgba(160,90,{"values":np.ones(16)},dict(DEFAULT_TEMPLATE,_quality="PREVIEW"));assert {"setup_ms","allocation_ms","draw_ms","glow_ms","final_copy_ms","total_ms"}<=set(renderer.last_profile)
def test_preview_glow_scale_preserves_shape():
    renderer=CPURenderer();state={"values":np.linspace(0,1,16,dtype=np.float32)};image=renderer.render_rgba(160,90,state,dict(DEFAULT_TEMPLATE,_quality="PREVIEW"));assert image.shape==(90,160,4) and image[:,:,3].max()>0
def test_resource_resolver_points_to_templates():
    from core.paths import resource_path
    assert resource_path("templates/01_clean_bars.json").exists()
