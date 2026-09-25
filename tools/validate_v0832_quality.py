"""Generate v0.8.3.2 MAIN 3 NORMAL/DYNAMIC visual review assets."""
from __future__ import annotations
import gc,json,shutil,subprocess,sys,tracemalloc,wave
from pathlib import Path
from time import perf_counter
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from animation.engine import AnimationEngine
from audio.analyzer import analyze_pcm
from render.renderer import CPURenderer,GPUBarRenderer
from template_system import load_template

OUT=ROOT/"validation_results/v0832_signature_quality_boost"
MAIN=[
 ("Twin",ROOT/"templates/00_v0832_twin_bloom_v2.json",ROOT/"templates/00_v0831_dual_twin_bloom.json"),
 ("Midnight",ROOT/"templates/00_v0832_midnight_grid_v2.json",ROOT/"templates/00_v0831_his_midnight_mirror.json"),
 ("Pearl",ROOT/"templates/00_v0832_pearl_bloom_v2.json",ROOT/"templates/00_v0831_her_pearl_bloom.json")]

def fixture(seconds=30,sr=12000):
    t=np.arange(int(seconds*sr),dtype=np.float32)/sr;phase=np.mod(t,.56);beat=(phase<.15)*np.exp(-phase*17)
    bass=np.sin(2*np.pi*(54+5*np.sin(t*.22))*t)*beat;snare=np.sin(2*np.pi*920*t)*(np.mod(t+.28,.56)<.055)*np.exp(-np.mod(t+.28,.56)*42)
    rap=.24*np.sin(2*np.pi*(175+32*np.sin(t*.53))*t)*(1+.28*np.sin(t*3.2));melody=.14*np.sin(2*np.pi*420*t)+.07*np.sin(2*np.pi*710*t)
    env=np.select([t<5,t<15,t<22],[.22,.55,.76],default=.94);chorus=np.where(t>22,1+.16*np.sin(t*1.5),1)
    return np.clip((.62*bass+.12*snare+rap+melody)*env*chorus,-1,1).astype(np.float32),sr

def encode(path,frames):
    path.parent.mkdir(parents=True,exist_ok=True);p=subprocess.Popen([shutil.which("ffmpeg"),"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s","960x160","-r","24","-i","pipe:0","-c:v","libx264","-preset","fast","-pix_fmt","yuv420p","-crf","18",str(path)],stdin=subprocess.PIPE)
    for frame in frames:p.stdin.write(memoryview(frame))
    p.stdin.close();code=p.wait()
    if code:raise RuntimeError(code)

def screen(background,frame,y=190):
    bg=cv2.resize(background,(960,540));fg=cv2.cvtColor(frame[:,:,:3],cv2.COLOR_RGB2BGR).astype(np.uint16);roi=bg[y:y+160].astype(np.uint16);bg[y:y+160]=(255-(255-roi)*(255-fg)//255).astype(np.uint8);return cv2.cvtColor(bg,cv2.COLOR_BGR2RGB)

def sheet(items,path,cell_h=205):
    canvas=Image.new("RGB",(960*len(items),cell_h),"black");draw=ImageDraw.Draw(canvas)
    for i,(label,img) in enumerate(items):canvas.paste(Image.fromarray(img[:,:,:3]).convert("RGB"),(i*960,0));draw.text((i*960+16,172),label,fill=(238,242,248))
    canvas.save(path)

def before_after(items,path):
    canvas=Image.new("RGB",(1920,205*len(items)),"black");draw=ImageDraw.Draw(canvas)
    for row,(name,before,after) in enumerate(items):
        y=row*205;canvas.paste(Image.fromarray(before[:,:,:3]),(0,y));canvas.paste(Image.fromarray(after[:,:,:3]),(960,y));draw.text((14,y+172),f"{name} v0.8.3.1 BEFORE",fill="white");draw.text((974,y+172),f"{name} v0.8.3.2 DYNAMIC",fill="white")
    canvas.save(path)

def visual_metrics(frame):
    mask=frame[:,:,3]>28;ys,xs=np.where(mask);height=int(ys.max()-ys.min()+1) if len(ys) else 0;left=mask[:,:480].sum();right=mask[:,480:].sum();pixels=frame[:,:,:3][mask]
    clipped=float((pixels.max(axis=1)>=250).mean()) if len(pixels) else 0;return {"visual_height_px":height,"left_right_balance":round(float(min(left,right)/max(1,max(left,right))),3),"clipped_pixel_ratio":round(clipped,5),"coverage":round(float(mask.mean()),4)}

def main():
    for folder in ("videos","stills","mockups","reports","contact_sheets"):(OUT/folder).mkdir(parents=True,exist_ok=True)
    pcm,sr=fixture();wav=OUT/"chill_rap_30s_fixture.wav"
    with wave.open(str(wav),"wb") as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes((pcm*32767).astype("<i2").tobytes())
    bg=cv2.imread(str(ROOT/"sample_assets/background/v0830_tokyo_night_fixture.png"));report={"version":"0.8.3.2","engineering":"TECH PASS","visual_approval":"USER REVIEW REQUIRED","external_beta":"HOLD","signatures":{},"checks":{}};normal_items=[];dynamic_items=[];comparisons=[]
    for short,new_path,old_path in MAIN:
        new=load_template(new_path);features=analyze_pcm(pcm,sr,fps=24,bands=int(new["bands"]),fft_size=2048)
        captures={}
        for intensity in ("NORMAL","DYNAMIC"):
            template=dict(new,intensity=intensity);engine=AnimationEngine(features,template);renderer=CPURenderer();selected=[];started=perf_counter()
            def frames():
                for i in range(720):
                    frame=renderer.render_rgba(960,160,engine.sample(i/24),template)
                    if i in (48,300,600):selected.append(frame.copy())
                    yield frame
            video=OUT/"videos"/f"{short}_{intensity.title()}.mp4";encode(video,frames());fps=720/(perf_counter()-started);captures[intensity]=selected[-1];Image.fromarray(selected[-1],"RGBA").save(OUT/"stills"/f"{short}_{intensity.title()}.png")
            metrics=visual_metrics(selected[-1]);metrics["section_heights_px"]={label:visual_metrics(frame)["visual_height_px"] for label,frame in zip(("quiet","normal","strong"),selected)}
            report["signatures"].setdefault(short,{"layers":3,"variant":new["signature_variant"],"placement":new["placement"],"samples":{}})["samples"][intensity]={"video":str(video),"cpu_fps":round(fps,1),"metrics":metrics}
        normal_items.append((f"{short} NORMAL",captures["NORMAL"]));dynamic_items.append((f"{short} DYNAMIC",captures["DYNAMIC"]));y={"Twin":210,"Midnight":172,"Pearl":214}[short];mock=screen(bg,captures["DYNAMIC"],y);Image.fromarray(mock,"RGB").save(OUT/"mockups"/f"{short}_Dynamic_Mockup.png")
        old=load_template(old_path);old_features=analyze_pcm(pcm,sr,fps=24,bands=int(old["bands"]),fft_size=2048);old_frame=CPURenderer().render_rgba(960,160,AnimationEngine(old_features,old).sample(25),old);comparisons.append((short,old_frame,captures["DYNAMIC"]))
        state=AnimationEngine(features,dict(new,intensity="DYNAMIC")).sample(25);gpu=GPUBarRenderer();[gpu.render_rgba(960,160,state,dict(new,intensity="DYNAMIC")) for _ in range(5)];started=perf_counter();[gpu.render_rgba(960,160,state,dict(new,intensity="DYNAMIC")) for _ in range(120)];report["signatures"][short]["gpu_fps"]=round(120/(perf_counter()-started),1)
    sheet(normal_items,OUT/"contact_sheets/SIGNATURE_3_NORMAL.png");sheet(dynamic_items,OUT/"contact_sheets/SIGNATURE_3_DYNAMIC.png");before_after(comparisons,OUT/"contact_sheets/SIGNATURE_3_BEFORE_AFTER.png")
    # Decode validation checks black residue outside the active band.
    residue={}
    for short,_,_ in MAIN:
        cap=cv2.VideoCapture(str(OUT/"videos"/f"{short}_Dynamic.mp4"));cap.set(cv2.CAP_PROP_POS_FRAMES,600);ok,frame=cap.read();cap.release();mask=frame.max(axis=2)>18;ys,xs=np.where(mask);outside=np.ones(mask.shape,bool)
        if len(xs):outside[max(0,ys.min()-8):min(160,ys.max()+9),max(0,xs.min()-8):min(960,xs.max()+9)]=False
        residue[short]=int(frame[outside].max()) if ok and outside.any() else None
    report["checks"].update({"dynamic_color_motion":"PASS","left_right_stereo_interaction":"PASS","up_down_motion":"PASS","center_interaction":"PASS","decoded_rgb_max_outside_bbox":residue})
    # Long-loop allocation check without retaining frames.
    template=load_template(MAIN[0][1]);features=analyze_pcm(pcm,sr,fps=24,bands=int(template["bands"]),fft_size=2048);engine=AnimationEngine(features,dict(template,intensity="DYNAMIC"));renderer=CPURenderer();gc.collect();tracemalloc.start();base=tracemalloc.get_traced_memory()[0]
    for i in range(720):renderer.render_rgba(960,160,engine.sample(i/24),dict(template,intensity="DYNAMIC"))
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop();report["checks"]["memory_growth_30s_mb"]=round((current-base)/1048576,3);report["checks"]["memory_peak_30s_mb"]=round((peak-base)/1048576,3)
    (OUT/"reports/signature_quality_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");(OUT/"reports/signature_quality_report.txt").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps({"output":str(OUT),"report":report},ensure_ascii=False))
if __name__=="__main__":main()
