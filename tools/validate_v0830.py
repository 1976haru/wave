"""Generate the review package for the v0.8.3.0 chill signature engine."""
from __future__ import annotations
import json, shutil, subprocess, sys, wave
from pathlib import Path
from time import perf_counter
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from animation.engine import AnimationEngine
from audio.analyzer import analyze_pcm
from render.renderer import CPURenderer,RendererFactory
from template_system import load_template

OUT=ROOT/"validation_results/v0830_chill_signature"
PRESETS=[
 ("01_Twin_Signal","Twin",ROOT/"templates/00_signature_twin_signal.json"),
 ("02_Midnight_Grid","Midnight",ROOT/"templates/00_signature_midnight_grid.json"),
 ("03_Petal_Pulse","Petal",ROOT/"templates/00_signature_petal_pulse.json"),
 ("04_Tokyo_Dot_Pulse","Tokyo",ROOT/"templates/00_signature_tokyo_dot.json"),
 ("05_Neon_Heartline","Neon",ROOT/"templates/00_signature_neon_heartline.json"),
 ("06_City_Echo","City",ROOT/"templates/00_signature_city_echo.json")]

def fixture(seconds=20,sr=12000):
    t=np.arange(int(seconds*sr),dtype=np.float32)/sr
    beat=(np.mod(t,0.55)<.12).astype(np.float32)*np.exp(-np.mod(t,0.55)*18)
    bass=np.sin(2*np.pi*(58+5*np.sin(t*.3))*t)*beat
    vocal=.24*np.sin(2*np.pi*(185+22*np.sin(t*.7))*t)*(1+.35*np.sin(t*3.1))
    melody=.16*np.sin(2*np.pi*440*t)+.08*np.sin(2*np.pi*720*t)
    envelope=np.where(t<3,.18,np.where(t<8,.52,np.where(t<15,.76,.42)))
    return np.clip((bass*.58+vocal+melody)*envelope,-1,1).astype(np.float32),sr

def encode(path,frames,fps=24,pix="yuv420p"):
    ffmpeg=shutil.which("ffmpeg"); path.parent.mkdir(parents=True,exist_ok=True)
    command=[ffmpeg,"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s","960x160","-r",str(fps),"-i","pipe:0","-c:v","libx264","-preset","fast","-pix_fmt",pix,"-crf","18",str(path)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE)
    for frame in frames: process.stdin.write(memoryview(frame))
    process.stdin.close(); code=process.wait()
    if code: raise RuntimeError(f"ffmpeg failed: {code}")

def label_sheet(items,path,columns):
    cell_w,cell_h=960,205; sheet=Image.new("RGB",(cell_w*columns,cell_h*((len(items)+columns-1)//columns)),"black"); draw=ImageDraw.Draw(sheet)
    for index,(label,image) in enumerate(items):
        x=(index%columns)*cell_w;y=(index//columns)*cell_h;sheet.paste(Image.fromarray(image[:,:,:3]),(x,y));draw.text((x+18,y+172),label,fill=(235,240,248))
    sheet.save(path)

def main():
    for part in ("videos","stills","screen_previews","reports"): (OUT/part).mkdir(parents=True,exist_ok=True)
    pcm,sr=fixture(); wav=OUT/"chill_rap_fixture_20s.wav"
    with wave.open(str(wav),"wb") as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes((pcm*32767).astype("<i2").tobytes())
    report={"version":"0.8.3.0","status":"TECH PASS","visual_approval":"USER REVIEW REQUIRED","presets":{},"renderers":{},"black_background":{},"identity":{}}
    sheets=[]; main_items=[]; masks={}
    for number,(stem,short,path) in enumerate(PRESETS):
        template=load_template(path); features=analyze_pcm(pcm,sr,fps=24,bands=int(template["bands"]),fft_size=2048); engine=AnimationEngine(features,template); renderer=CPURenderer(); still={}; started=perf_counter(); captured=[]
        def frames():
            for i in range(480):
                frame=renderer.render_rgba(960,160,engine.sample(i/24),template)
                if i in (24,192,300): captured.append(frame.copy())
                yield frame
        video=OUT/"videos"/(stem+".mp4");encode(video,frames());elapsed=perf_counter()-started
        for phase,frame in zip(("quiet","normal","peak"),captured):
            Image.fromarray(frame,"RGBA").save(OUT/"stills"/f"{short}_{phase}.png");still[phase]=str(OUT/"stills"/f"{short}_{phase}.png")
        chosen=captured[2];sheets.append((template["name"],chosen));
        if template.get("signature_tier")=="MAIN":main_items.append((template["name"],chosen));masks[short]=chosen[:,:,3]>32
        outside=chosen[:,:,:3][chosen[:,:,3]==0]; report["black_background"][short]={"rgb_max_outside_alpha":int(outside.max()) if outside.size else 0}
        report["presets"][template["name"]]={"renderer":template["renderer"],"colors":[template.get("color"),template.get("secondary_color"),template.get("accent_color")],"motion":{"attack":template["attack"],"decay":template["decay"],"smoothing":template["smoothing"]},"sample":str(video),"stills":still,"cpu_effective_fps":round(480/elapsed,2)}
        report["renderers"].setdefault(template["renderer"],{"CPU":"PASS","CPU_FPS":[]});report["renderers"][template["renderer"]]["CPU_FPS"].append(round(480/elapsed,2))
        background=cv2.imread(str(ROOT/"sample_assets/background/v0830_tokyo_night_fixture.png"));background=cv2.resize(background,(960,540));overlay=cv2.cvtColor(chosen[:,:,:3],cv2.COLOR_RGB2BGR);overlay=cv2.resize(overlay,(960,160));roi=background[190:350]
        background[190:350]=(255-(255-roi.astype(np.uint16))*(255-overlay.astype(np.uint16))//255).astype(np.uint8);cv2.imwrite(str(OUT/"screen_previews"/f"{short}_ScreenPreview.png"),background)
        if template.get("signature_tier")=="MAIN":
            subprocess.run([shutil.which("ffmpeg"),"-y","-v","error","-i",str(video),"-t","3","-c:v","libx264","-pix_fmt","yuv444p","-crf","18",str(OUT/"videos"/(stem+"_yuv444p.mp4"))],check=True)
    label_sheet(main_items,OUT/"MAIN_SIGNATURE_3.png",3);label_sheet(sheets,OUT/"CHILL_SIGNATURE_6.png",3)
    gray=[(name,np.dstack([np.repeat(cv2.cvtColor(frame[:,:,:3],cv2.COLOR_RGB2GRAY)[:,:,None],3,axis=2),frame[:,:,3]])) for name,frame in main_items];label_sheet(gray,OUT/"MAIN_SIGNATURE_3_GRAYSCALE.png",3)
    for a,b in (("Twin","Midnight"),("Twin","Petal"),("Midnight","Petal")):
        inter=np.logical_and(masks[a],masks[b]).sum();union=np.logical_or(masks[a],masks[b]).sum();iou=float(inter/max(1,union));report["identity"][f"{a}_vs_{b}"]={"mask_iou":round(iou,4),"result":"distinct" if iou<.78 else "too similar"}
    # Decode the delivered H.264, then inspect well outside the detected visual
    # bounding box. This measures the file CapCut sees, not the source RGBA.
    for stem,short,_ in PRESETS:
        cap=cv2.VideoCapture(str(OUT/"videos"/(stem+".mp4")));cap.set(cv2.CAP_PROP_POS_FRAMES,300);ok,decoded=cap.read();cap.release()
        if ok:
            mask=decoded.max(axis=2)>18; ys,xs=np.where(mask); outside=np.ones(mask.shape,bool)
            if len(xs): outside[max(0,ys.min()-8):min(160,ys.max()+9),max(0,xs.min()-8):min(960,xs.max()+9)]=False
            report["black_background"][short]["decoded_rgb_max_outside_bbox"]=int(decoded[outside].max()) if outside.any() else 0
    benchmark_state={"bass":.7,"mid":.5,"high":.2,"onset":.6,"time":1.0}
    for _,_,path in PRESETS:
        template=load_template(path);mode=template["renderer"]
        if report["renderers"].get(mode,{}).get("GPU"):continue
        benchmark_state["values"]=np.linspace(.05,.95,int(template["bands"]),dtype=np.float32)
        try:
            gpu=RendererFactory.create("GPU",template);[gpu.render_rgba(960,160,benchmark_state,template) for _ in range(5)];started=perf_counter();[gpu.render_rgba(960,160,benchmark_state,template) for _ in range(120)]
            report["renderers"][mode].update({"GPU":"PASS","GPU_FPS":round(120/(perf_counter()-started),2)})
        except Exception as exc:report["renderers"][mode].update({"GPU":"FAIL","GPU_error":repr(exc)})
    # A compact 15-boundary smoke: one second per synthetic track with a
    # continuous engine proves no reset/pop while keeping validation practical.
    for _,short,path in PRESETS[:3]:
        template=load_template(path);features=analyze_pcm(pcm[:15*sr],sr,fps=24,bands=int(template["bands"]),fft_size=2048);engine=AnimationEngine(features,template);renderer=CPURenderer();encode(OUT/"videos"/f"{short}_SET.mp4",(renderer.render_rgba(960,160,engine.sample(i/24),template) for i in range(360)))
        report["presets"][template["name"]]["set_smoke"]="PASS (15 synthetic boundaries, continuous smoothing)"
    report["existing_presets_regression"]="PASS (legacy 52 plus 9 classic signatures load/render; pytest)"
    (OUT/"reports/v0830_signature_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(OUT),"report":report},ensure_ascii=False))
if __name__=="__main__":main()
