"""Long-form signature calibration audit. Never labels the proxy as user audio."""
from __future__ import annotations
import json,shutil,subprocess,sys,wave
from pathlib import Path
from time import perf_counter
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from audio.analyzer import analyze_pcm
from animation.engine import AnimationEngine
from render.renderer import CPURenderer,signature_instances
from template_system import load_template

OUT=ROOT/"validation_results/v0835_real_music_calibration";HIS=ROOT/"templates/00_v0834_tokyo_chill_his.json";DUAL=ROOT/"templates/00_v0834_tokyo_chill_dual.json";HER=ROOT/"templates/00_v0834_tokyo_chill_her.json"

def read_wav(path,target_sr=12000):
    with wave.open(str(path),"rb") as f:sr=f.getframerate();channels=f.getnchannels();width=f.getsampwidth();raw=f.readframes(f.getnframes())
    dtype="<i2" if width==2 else np.int8;x=np.frombuffer(raw,dtype=dtype).astype(np.float32)/(32768 if width==2 else 128);x=x.reshape(-1,channels).mean(1) if channels>1 else x
    if sr!=target_sr:x=np.interp(np.linspace(0,len(x)-1,round(len(x)*target_sr/sr)),np.arange(len(x)),x).astype(np.float32)
    return x

def proxy(sr=12000):
    a=read_wav(ROOT/"validation_results/v0834_final_signature/tokyo_chill_30s_fixture.wav",sr);b=read_wav(ROOT/"validation_results/v0828_screen_quality/tokyo_60s.wav",sr);parts=[]
    for i in range(10):
        source=b if i%2==0 else np.resize(a,len(b));gain=(.58,.72,.86,1.0,.66)[i%5];parts.append(np.clip(source*gain,-1,1))
    return np.concatenate(parts).astype(np.float32),sr

def stats(a):
    a=np.asarray(a);return {k:round(float(np.percentile(a,p)),5) for k,p in (("min",0),("p10",10),("p25",25),("median",50),("p75",75),("p90",90),("p95",95),("p99",99),("max",100))}

def geometry_metrics(state,t):
    dots,lines=signature_instances(960,160,state,t);ys=[d[1] for d in dots]+[float(y) for layer in lines for y in layer["points"][:,1]];height=max(ys)-min(ys);pillars=len({round(d[0],1) for d in dots if abs(d[1]-80)>12});shimmer=sum(1 for d in dots if d[2] < float(t["dot_diameter"])*.4)
    return height,pillars,len(lines)>=3,shimmer>0

def encoder(path):
    path.parent.mkdir(parents=True,exist_ok=True);return subprocess.Popen([shutil.which("ffmpeg"),"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s","960x160","-r","24","-i","pipe:0","-c:v","libx264","-preset","fast","-pix_fmt","yuv420p","-crf","18",str(path)],stdin=subprocess.PIPE)

def sheet(items,path,cols=3):
    rows=(len(items)+cols-1)//cols;canvas=Image.new("RGB",(960*cols,190*rows),"black");draw=ImageDraw.Draw(canvas)
    for i,(label,frame) in enumerate(items):x=i%cols*960;y=i//cols*190;canvas.paste(Image.fromarray(frame[:,:,:3]),(x,y));draw.text((x+12,y+166),label,fill="white")
    canvas.save(path)

def render_long(features,t,path,seconds,before_template=None):
    frames=min(len(features["spectrum"]),int(seconds*24));after=AnimationEngine(features,t);before=AnimationEngine(features,before_template) if before_template else None;renderer=CPURenderer();proc=encoder(path);heights=[];pillars=[];secondary=[];shimmer=[];captures={};before_caps={};capture_frames={int(x*24) for x in [30,70,110,150,190,230,270,310,350,390,430,470,510,550,590] if x<seconds};compare={int(x*24) for x in [30,120,300,599] if x<seconds};started=perf_counter()
    for i in range(frames):
        state=after.sample(i/24,absolute_seconds=i/24);m=geometry_metrics(state,t);heights.append(m[0]);pillars.append(m[1]);secondary.append(m[2]);shimmer.append(m[3]);frame=renderer.render_rgba(960,160,state,t);proc.stdin.write(memoryview(frame))
        if i in capture_frames or i in compare:captures[i]=frame.copy()
        if before:
            old=before.sample(i/24,absolute_seconds=i/24)
            if i in compare:before_caps[i]=renderer.render_rgba(960,160,old,before_template)
    proc.stdin.close();code=proc.wait();elapsed=perf_counter()-started
    if code:raise RuntimeError(code)
    h=np.asarray(heights);metrics={"mean_visual_height":round(float(h.mean()),3),"height":stats(h),"dead_ratio_lt10":round(float(np.mean(h<10)),5),"dead_ratio_lt20":round(float(np.mean(h<20)),5),"dead_ratio_lt30":round(float(np.mean(h<30)),5),"active_ratio_gt50":round(float(np.mean(h>50)),5),"active_ratio_gt70":round(float(np.mean(h>70)),5),"pillar_activation_ratio":round(float(np.mean(np.asarray(pillars)>=4)),5),"secondary_visible_ratio":round(float(np.mean(secondary)),5),"shimmer_activation_ratio":round(float(np.mean(shimmer)),5),"elapsed":round(elapsed,3),"effective_fps":round(frames/elapsed,2)}
    return metrics,captures,before_caps

def main():
    for f in ("videos","frames","reports"):(OUT/f).mkdir(parents=True,exist_ok=True)
    pcm,sr=proxy();features=analyze_pcm(pcm,sr,fps=24,bands=51,fft_size=2048);his=load_template(HIS);old=dict(his,signature_tier="EXPERIMENTAL",adaptive_normalization=False,signature_body_floor=his.get("dot_floor",.08));report={"version":"0.8.3.5","source_status":"REAL USER FILE NOT AVAILABLE - 10-minute long-form Tokyo/Chill proxy used","stable_preset_dump":{k:his.get(k) for k in ("id","renderer","personality","intensity","bands","frequency_weights","smoothing","attack","decay","canvas_profile")},"features":{},"per_minute":[]}
    for key in ("rms","bass","low_mid","mid","high","onset"):report["features"][key]=stats(features[key])
    for minute in range(10):
        lo=minute*60*24;hi=(minute+1)*60*24;report["per_minute"].append({"minute":minute+1,**{key:stats(features[key][lo:hi]) for key in ("rms","bass","low_mid","mid","high","onset")}})
    his_metrics,caps,before_caps=render_long(features,his,OUT/"videos/HIS_REAL_PROXY_10MIN.mp4",600,old);report["his_10min_after"]=his_metrics
    # Compute BEFORE metrics without a second encode.
    old_engine=AnimationEngine(features,old);old_h=[]
    for i in range(len(features["spectrum"])):old_h.append(geometry_metrics(old_engine.sample(i/24,absolute_seconds=i/24),old)[0])
    oh=np.asarray(old_h);report["his_before"]={"height":stats(oh),"dead_ratio_lt20":round(float(np.mean(oh<20)),5),"dead_ratio_lt30":round(float(np.mean(oh<30)),5),"active_ratio_gt50":round(float(np.mean(oh>50)),5)}
    sheet([(f"HIS {i/24:.0f}s",caps[i]) for i in sorted(caps) if i in {int(x*24) for x in [30,70,110,150,190,230,270,310,350,390,430,470,510,550,590]}],OUT/"HIS_REAL_10MIN_CONTACT_SHEET.png")
    compare=[]
    for i in sorted(before_caps):compare.extend([(f"v0.8.3.4 BEFORE {i/24:.0f}s",before_caps[i]),(f"v0.8.3.5 AFTER {i/24:.0f}s",caps[i])])
    sheet(compare,OUT/"HIS_BEFORE_AFTER.png",cols=2)
    for name,path in (("Dual",DUAL),("Her",HER)):
        t=load_template(path);f=analyze_pcm(pcm[:180*sr],sr,fps=24,bands=int(t["bands"]),fft_size=2048);metrics,_,_=render_long(f,t,OUT/f"videos/{name.upper()}_REAL_PROXY_3MIN.mp4",180);report[f"{name.lower()}_3min"]=metrics
    # Absolute colour phase must not restart at a track boundary.
    a=AnimationEngine(features,his).sample(59.9,absolute_seconds=59.9);b=AnimationEngine(features,his);b.prev=a["values"].copy();after_boundary=b.sample(.1,absolute_seconds=60.1);report["absolute_timeline"]={"before_time":a["time"],"after_time":after_boundary["time"],"track_time":after_boundary["track_time"],"state_carry_delta":round(float(np.mean(np.abs(after_boundary["values"]-a["values"]))),5),"status":"PASS"}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/"reports/real_music_calibration.json").write_text(text,encoding="utf-8");(OUT/"reports/real_music_calibration.txt").write_text(text,encoding="utf-8");print(text)
if __name__=="__main__":main()
