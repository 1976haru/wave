import json, wave
from pathlib import Path
import numpy as np
import pytest
from audio import analyzer
from audio.analyzer import AnalysisSettings, analyze_file, analyze_pcm, decode_audio
from animation.engine import AnimationEngine
from pipeline.batch import BatchRunner
from render.renderer import CPURenderer, RendererFactory
from template_system import load_template, migrate_template, save_template

def tone(frequency=110,duration=1,sr=44100):
    t=np.arange(int(sr*duration))/sr
    return (.8*np.sin(2*np.pi*frequency*t)).astype(np.float32),sr

def write_wav(path,frequency=220):
    data,sr=tone(frequency)
    with wave.open(str(path),"wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(sr); output.writeframes((data*32767).astype("<i2").tobytes())

def test_audio_decoding(tmp_path):
    path=tmp_path/"tone.wav"; write_wav(path); decoded,sr=decode_audio(path)
    assert sr==44100 and len(decoded)==44100 and np.max(np.abs(decoded))>.5

def test_fft_rms_onset_and_frequency_bands():
    low,sr=tone(100); high,_=tone(8000); transient=low.copy(); transient[len(transient)//2:]*=.1
    lf=analyze_pcm(low,sr,bands=32); hf=analyze_pcm(high,sr,bands=32); tf=analyze_pcm(transient,sr,bands=32)
    assert lf["bass"].mean()>lf["high"].mean()
    assert hf["high"].mean()>hf["bass"].mean()
    assert lf["rms"].max()>.5 and tf["onset"].max()>.5

def test_cache_hit_and_invalidation(tmp_path):
    source=tmp_path/"audio.wav"; write_wav(source,110); cache=tmp_path/"cache"; settings=AnalysisSettings(bands=16)
    first,hit=analyze_file(source,settings,cache); second,hit2=analyze_file(source,settings,cache)
    assert not hit and hit2 and np.array_equal(first["spectrum"],second["spectrum"])
    write_wav(source,440); _,hit3=analyze_file(source,settings,cache)
    assert not hit3 and len(list(cache.glob("*.npz")))==2

def _features():
    return {"spectrum":np.array([[.1,.1,.1,.1,.1,.1],[1,1,1,1,1,1]],np.float32),"rms":np.ones(2),"bass":np.array([.1,1]),"mid":np.array([.1,.5]),"high":np.array([.1,.2]),"onset":np.array([0,1]),"fps":np.array([1])}

def test_attack_decay_and_band_weighting():
    quick=AnimationEngine(_features(),{"attack":0,"decay":.9,"smoothing":0,"bass_weight":2,"mid_weight":1,"high_weight":.2,"onset_boost":0})
    quick.sample(0); raised=quick.sample(1)["values"]
    assert raised[0]>raised[-1]
    decay=AnimationEngine(_features(),{"attack":0,"decay":.95,"smoothing":0}); decay.sample(1); held=decay.sample(0)["values"]
    assert held.mean()>.1

def test_template_save_load_and_old_migration(tmp_path):
    migrated=migrate_template({"style":"dot","band_count":20,"barWidth":.4,"colour":"#123456"})
    assert migrated["renderer"]=="dot" and migrated["bands"]==20 and migrated["version"]=="0.5.1"
    path=tmp_path/"preset.json"; save_template(path,migrated); assert load_template(path)["color"]=="#123456"

def test_true_alpha_cpu_renderer():
    image=CPURenderer().render_rgba(160,90,{"values":np.ones(8)},{"renderer":"bars","color":"#000000","opacity":.5})
    assert image[:,:,3].max()>0 and image[:,:,:3].max()==0

def test_gpu_failure_cpu_fallback(monkeypatch):
    import render.renderer as module
    class Broken:
        def __init__(self): raise RuntimeError("no GPU")
    monkeypatch.setattr(module,"GPUBarRenderer",Broken)
    auto=RendererFactory.create("AUTO"); image=auto.render_rgba(80,40,{"values":np.ones(4)},{"renderer":"bars"}); assert auto.name=="CPU" and image.shape==(40,80,4)
    with pytest.raises(RuntimeError): RendererFactory.create("GPU")

def test_batch_partial_failure_and_report(tmp_path):
    def fake(source,target,template,options=None,cancel=None):
        if "bad" in str(source): raise ValueError("broken")
        return {"output":str(target)}
    results=BatchRunner().run(["good.wav","bad.wav","next.wav"],tmp_path,{},render_fn=fake)
    assert [x["status"] for x in results]==["success","failed","success"]
    assert json.loads((tmp_path/"error_report.json").read_text())[0]["file"]=="bad.wav"

def test_batch_cancel(tmp_path):
    runner=BatchRunner()
    def fake(source,target,template,options=None,cancel=None): runner.cancel(); return {}
    results=runner.run(["one.wav","two.wav"],tmp_path,{},render_fn=fake)
    assert len(results)==1 and runner.cancelled
