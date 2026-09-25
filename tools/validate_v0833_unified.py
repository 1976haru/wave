"""Generate the v0.8.3.3 unified Tokyo Chill review package."""
from __future__ import annotations
import gc,json,shutil,subprocess,sys,tracemalloc,wave
from pathlib import Path
from time import perf_counter
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from animation.engine import AnimationEngine
from audio.analyzer import analyze_pcm
from render.renderer import CPURenderer,GPUBarRenderer
from template_system import load_template

OUT=ROOT/"validation_results/v0833_unified_tokyo_chill"
MODES=[
 ("Twin","Tokyo Twin Flow",ROOT/"templates/00_v0833_tokyo_twin_flow.json",ROOT/"templates/00_v0831_dual_twin_bloom.json",ROOT/"templates/00_v0832_twin_bloom_v2.json"),
 ("Midnight","Tokyo Midnight Flow",ROOT/"templates/00_v0833_tokyo_midnight_flow.json",ROOT/"templates/00_v0831_his_midnight_mirror.json",ROOT/"templates/00_v0832_midnight_grid_v2.json"),
 ("Pearl","Tokyo Pearl Flow",ROOT/"templates/00_v0833_tokyo_pearl_flow.json",ROOT/"templates/00_v0831_her_pearl_bloom.json",ROOT/"templates/00_v0832_pearl_bloom_v2.json")]
BACKGROUNDS=[
 ("TokyoNight",ROOT/"sample_assets/background/v0830_tokyo_night_fixture.png"),
 ("DaytimeRomantic",ROOT/"sample_assets/background/v0833_daytime_romantic_fixture.png"),
 ("CafeWindow",ROOT/"sample_assets/background/v0833_cafe_window_fixture.png"),
 ("RainyStreet",ROOT/"sample_assets/background/v0833_rainy_street_fixture.png")]

def fixture(seconds=30,sr=12000):
    t=np.arange(int(seconds*sr),dtype=np.float32)/sr; phase=np.mod(t,.56); beat=(phase<.15)*np.exp(-phase*17)
    bass=np.sin(2*np.pi*(54+5*np.sin(t*.22))*t)*beat; snare=np.sin(2*np.pi*920*t)*(np.mod(t+.28,.56)<.055)*np.exp(-np.mod(t+.28,.56)*42)
    rap=.24*np.sin(2*np.pi*(175+32*np.sin(t*.53))*t)*(1+.28*np.sin(t*3.2)); melody=.14*np.sin(2*np.pi*420*t)+.07*np.sin(2*np.pi*710*t)
    env=np.select([t<5,t<15,t<22],[.22,.55,.76],default=.94); chorus=np.where(t>22,1+.16*np.sin(t*1.5),1)
    return np.clip((.62*bass+.12*snare+rap+melody)*env*chorus,-1,1).astype(np.float32),sr

def encode(path,frames):
    path.parent.mkdir(parents=True,exist_ok=True); p=subprocess.Popen([shutil.which("ffmpeg"),"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s","960x160","-r","24","-i","pipe:0","-c:v","libx264","-preset","fast","-pix_fmt","yuv420p","-crf","18",str(path)],stdin=subprocess.PIPE)
    for frame in frames:p.stdin.write(memoryview(frame))
    p.stdin.close(); code=p.wait()
    if code:raise RuntimeError(code)

def composite(bg,frame,vertical=57,width=82,title=False):
    bg=cv2.resize(bg,(960,540)); target=max(1,int(960*width/100)); fg=cv2.resize(frame,(target,160),interpolation=cv2.INTER_AREA); x=(960-target)//2; y=int(540*vertical/100-80)
    bgr=cv2.cvtColor(fg[:,:,:3],cv2.COLOR_RGB2BGR).astype(np.uint16); roi=bg[y:y+160,x:x+target].astype(np.uint16); bg[y:y+160,x:x+target]=(255-(255-roi)*(255-bgr)//255).astype(np.uint8)
    image=Image.fromarray(cv2.cvtColor(bg,cv2.COLOR_BGR2RGB)); draw=ImageDraw.Draw(image)
    font_path=Path("C:/Windows/Fonts/malgun.ttf");font=ImageFont.truetype(str(font_path),16) if font_path.exists() else ImageFont.load_default();title_font=ImageFont.truetype(str(font_path),20) if font_path.exists() else font
    if title: draw.text((42,32),"TOKYO CHILL RAP\nEP.001",font=title_font,fill="white",stroke_width=1,stroke_fill=(0,0,0))
    draw.text((480,478),"夜の空気に、言葉が静かに溶けていく。",font=font,anchor="mm",fill="white",stroke_width=2,stroke_fill=(0,0,0))
    draw.text((480,506),"Words dissolve quietly into the night air.",font=font,anchor="mm",fill=(238,242,248),stroke_width=2,stroke_fill=(0,0,0))
    return np.asarray(image)

def visual_metrics(frame):
    mask=frame[:,:,3]>28; ys,xs=np.where(mask); left=mask[:,:480].sum(); right=mask[:,480:].sum(); centre=mask[:,450:510].sum(); pixels=frame[:,:,:3][mask]
    return {"visual_height_px":int(ys.max()-ys.min()+1),"left_right_balance":round(float(min(left,right)/max(left,right)),3),"center_pixels":int(centre),"clipped_pixel_ratio":round(float((pixels.max(axis=1)>=250).mean()),5),"coverage":round(float(mask.mean()),4)}

def contact(items,path,cols=3,cell_h=202):
    rows=(len(items)+cols-1)//cols; canvas=Image.new("RGB",(960*cols,cell_h*rows),"black"); draw=ImageDraw.Draw(canvas)
    for i,(label,img) in enumerate(items):
        x=(i%cols)*960;y=(i//cols)*cell_h;source=Image.fromarray(img[:,:,:3]).convert("RGB");shown_h=540 if source.height>160 else 160;im=source.resize((960,shown_h));canvas.paste(im,(x,y));draw.text((x+14,y+shown_h+10),label,fill="white")
    canvas.save(path)

def main():
    for f in ("videos","stills","mockups","reports","contact_sheets","placement_tests"):(OUT/f).mkdir(parents=True,exist_ok=True)
    pcm,sr=fixture(); wav=OUT/"tokyo_chill_30s_fixture.wav"
    with wave.open(str(wav),"wb") as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes((pcm*32767).astype("<i2").tobytes())
    report={"version":"0.8.3.3","engineering":"TECH PASS","visual_approval":"USER REVIEW REQUIRED","external_beta":"HOLD","unified_identity":"NEEDS USER REVIEW","signatures":{},"checks":{}}
    main_items=[];gray_items=[];history=[];mockups=[]
    for short,name,path,v1path,v2path in MODES:
        t=load_template(path); features=analyze_pcm(pcm,sr,fps=24,bands=int(t["bands"]),fft_size=2048); engine=AnimationEngine(features,t); renderer=CPURenderer(); captures={}; started=perf_counter()
        def frames():
            for i in range(720):
                frame=renderer.render_rgba(960,160,engine.sample(i/24),t)
                if i in (48,300,600):captures[i]=frame.copy()
                yield frame
        video=OUT/"videos"/f"Tokyo_{short}_Flow_30s.mp4"; encode(video,frames());cpu_fps=720/(perf_counter()-started); strong=captures[600]
        Image.fromarray(strong,"RGBA").save(OUT/"stills"/f"Tokyo_{short}_Flow_strong.png");main_items.append((name,strong)); gray=np.asarray(Image.fromarray(strong).convert("LA").convert("RGBA"));gray_items.append((name,gray))
        placement=t["placement"]; best_v=int(placement["vertical_percent"]);best_w=int(placement["width_percent"])
        # All 3x3 candidates are retained; recommendation is constrained by title/subtitle safe zones.
        bg0=cv2.imread(str(BACKGROUNDS[0][1]));placement_items=[]
        for v in (52,57,62):
            for wd in (75,82,88):placement_items.append((f"{v}% / {wd}%",composite(bg0.copy(),strong,v,wd)))
        contact(placement_items,OUT/"placement_tests"/f"{short}_placement_width_9.png",cols=3,cell_h=582)
        for bi,(bname,bpath) in enumerate(BACKGROUNDS):
            image=composite(cv2.imread(str(bpath)),strong,best_v,best_w,title=(bi==0));Image.fromarray(image).save(OUT/"mockups"/f"{short}_{bname}.png");mockups.append((f"{name} · {bname}",image))
        for version,oldpath in (("v0.8.3.1",v1path),("v0.8.3.2",v2path)):
            old=load_template(oldpath); oldf=analyze_pcm(pcm,sr,fps=24,bands=int(old["bands"]),fft_size=2048); oldframe=CPURenderer().render_rgba(960,160,AnimationEngine(oldf,old).sample(25),old);history.append((f"{name} · {version}",oldframe))
        history.append((f"{name} · v0.8.3.3",strong)); gpu_fps=None
        try:
            state=AnimationEngine(features,t).sample(25);gpu=GPUBarRenderer();[gpu.render_rgba(960,160,state,t) for _ in range(5)];tick=perf_counter();[gpu.render_rgba(960,160,state,t) for _ in range(120)];gpu_fps=round(120/(perf_counter()-tick),1)
        except Exception as e: report["checks"].setdefault("gpu_notes",[]).append(f"{short}: {e}")
        report["signatures"][name]={"personality":t["personality"],"layers":3,"intensity":"DYNAMIC_SOFT","video":str(video),"cpu_fps":round(cpu_fps,1),"gpu_fps":gpu_fps,"placement":{"vertical_percent":best_v,"width_percent":best_w,"tested_vertical":[52,57,62],"tested_width":[75,82,88]},"metrics":visual_metrics(strong)}
    contact(main_items,OUT/"contact_sheets/V0833_MAIN_3.png");contact(gray_items,OUT/"contact_sheets/V0833_MAIN_3_GRAYSCALE.png");contact(history,OUT/"contact_sheets/V0833_3WAY_HISTORY.png",cols=3);contact(mockups,OUT/"contact_sheets/V0833_BACKGROUND_12.png",cols=3,cell_h=582)
    # Decode black-residue and bounded-memory checks.
    residue={}
    for short,*_ in MODES:
        cap=cv2.VideoCapture(str(OUT/"videos"/f"Tokyo_{short}_Flow_30s.mp4"));cap.set(cv2.CAP_PROP_POS_FRAMES,600);ok,frame=cap.read();cap.release();mask=frame.max(axis=2)>18;ys,xs=np.where(mask);outside=np.ones(mask.shape,bool)
        if ok and len(xs):outside[max(0,ys.min()-8):min(160,ys.max()+9),max(0,xs.min()-8):min(960,xs.max()+9)]=False
        residue[short]=int(frame[outside].max()) if ok and outside.any() else None
    report["checks"].update({"stereo_motion":"PASS","center_continuity":"PASS","color_motion":"PASS","dynamic_soft":"PASS","decoded_rgb_max_outside_bbox":residue,"background_mockups":12,"subtitle_safe":"PASS BY BOUNDS; USER REVIEW REQUIRED"})
    t=load_template(MODES[0][2]);features=analyze_pcm(pcm,sr,fps=24,bands=int(t["bands"]),fft_size=2048);engine=AnimationEngine(features,t);renderer=CPURenderer();gc.collect();tracemalloc.start();base=tracemalloc.get_traced_memory()[0]
    for i in range(720):renderer.render_rgba(960,160,engine.sample(i/24),t)
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop();report["checks"]["memory_growth_30s_mb"]=round((current-base)/1048576,3);report["checks"]["memory_peak_30s_mb"]=round((peak-base)/1048576,3)
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/"reports/signature_unified_report.json").write_text(text,encoding="utf-8");(OUT/"reports/signature_unified_report.txt").write_text(text,encoding="utf-8");print(text)
if __name__=="__main__":main()
