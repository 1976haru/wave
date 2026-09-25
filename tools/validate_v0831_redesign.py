"""Build the v0.8.3.1 nine-candidate visual review package."""
from __future__ import annotations
import json,shutil,subprocess,sys,wave
from pathlib import Path
from time import perf_counter
import cv2,numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from animation.engine import AnimationEngine
from audio.analyzer import analyze_pcm
from render.renderer import CPURenderer
from template_system import load_template

OUT=ROOT/"validation_results/v0831_signature_redesign"
CANDIDATES=[
 ("Dual","01_Symmetric_Twin_Bloom",ROOT/"templates/00_v0831_dual_twin_bloom.json"),
 ("Dual","02_Crossfade_Conversation",ROOT/"templates/00_v0831_dual_crossfade.json"),
 ("Dual","03_Echo_Dialogue",ROOT/"templates/00_v0831_dual_echo_dialogue.json"),
 ("His","04_Urban_Stereo_Pulse",ROOT/"templates/00_v0831_his_urban_stereo.json"),
 ("His","05_Midnight_Mirror_Grid",ROOT/"templates/00_v0831_his_midnight_mirror.json"),
 ("His","06_Blue_Structure_Wave",ROOT/"templates/00_v0831_his_blue_structure.json"),
 ("Her","07_Silk_Mirror_Ribbon",ROOT/"templates/00_v0831_her_silk_ribbon.json"),
 ("Her","08_Pearl_Stereo_Bloom",ROOT/"templates/00_v0831_her_pearl_bloom.json"),
 ("Her","09_Lavender_Breathing_Line",ROOT/"templates/00_v0831_her_lavender_line.json")]
BEST={"Symmetric Twin Bloom","Midnight Mirror Grid","Pearl Stereo Bloom"}

def fixture(seconds=10,sr=12000):
    t=np.arange(int(seconds*sr),dtype=np.float32)/sr; phase=np.mod(t,.54)
    beat=(phase<.15)*np.exp(-phase*17);bass=np.sin(2*np.pi*(55+4*np.sin(t*.25))*t)*beat
    vocal=.25*np.sin(2*np.pi*(180+28*np.sin(t*.62))*t)*(1+.30*np.sin(t*2.7));melody=.15*np.sin(2*np.pi*430*t)+.07*np.sin(2*np.pi*690*t)
    envelope=np.where(t<1.8,.26,np.where(t<6.8,.72,.48));return np.clip((.62*bass+vocal+melody)*envelope,-1,1).astype(np.float32),sr

def encode(path,frames):
    path.parent.mkdir(parents=True,exist_ok=True);p=subprocess.Popen([shutil.which("ffmpeg"),"-y","-v","error","-f","rawvideo","-pix_fmt","rgba","-s","960x160","-r","24","-i","pipe:0","-c:v","libx264","-preset","fast","-pix_fmt","yuv420p","-crf","18",str(path)],stdin=subprocess.PIPE)
    for frame in frames:p.stdin.write(memoryview(frame))
    p.stdin.close();code=p.wait()
    if code:raise RuntimeError(f"ffmpeg failed {code}")

def gray_rgba(frame):
    g=cv2.cvtColor(frame[:,:,:3],cv2.COLOR_RGB2GRAY);return np.dstack((g,g,g,frame[:,:,3]))

def screen(background,frame):
    bg=cv2.resize(background,(960,540));fg=cv2.cvtColor(frame[:,:,:3],cv2.COLOR_RGB2BGR);roi=bg[190:350].astype(np.uint16);fg=fg.astype(np.uint16);bg[190:350]=(255-(255-roi)*(255-fg)//255).astype(np.uint8);return cv2.cvtColor(bg,cv2.COLOR_BGR2RGB)

def sheet(items,path,columns,cell_h=205):
    rows=(len(items)+columns-1)//columns;canvas=Image.new("RGB",(960*columns,cell_h*rows),"black");draw=ImageDraw.Draw(canvas)
    for i,(label,img) in enumerate(items):
        x=(i%columns)*960;y=(i//columns)*cell_h;rgb=img[:,:,:3] if img.ndim==3 else img;canvas.paste(Image.fromarray(rgb).convert("RGB"),(x,y));draw.text((x+16,y+171),label,fill=(238,242,248))
    canvas.save(path)

def metrics(frames):
    masks=[f[:,:,3]>28 for f in frames];areas=np.array([m.sum() for m in masks],np.float32);peak=frames[-1];mask=peak[:,:,3]>28;mid=mask.shape[1]//2;left=mask[:,:mid].sum();right=mask[:,mid:].sum();balance=min(left,right)/max(1,max(left,right));coverage=float(mask.sum()/mask.size)
    motion=float(np.mean([np.logical_xor(a,b).sum()/max(1,np.logical_or(a,b).sum()) for a,b in zip(masks[:-1],masks[1:])]))
    pixels=peak[:,:,:3][mask];colorfulness=float(np.std(pixels,axis=0).mean()/128) if len(pixels) else 0
    return {"left_right_balance":round(float(balance),3),"coverage":round(coverage,4),"motion_change":round(motion,3),"palette_variation":round(colorfulness,3),"static_readability":"GOOD" if coverage>.008 else "WEAK","motion_attraction":"GOOD" if motion>.08 else "SUBTLE","screen_suitability":"GOOD" if .008<coverage<.12 else "REVIEW"}

def main():
    for folder in ("videos","previews","grayscale","capcut_mockups","reports","contact_sheets"):(OUT/folder).mkdir(parents=True,exist_ok=True)
    pcm,sr=fixture();wav=OUT/"chill_rap_fixture_10s.wav"
    with wave.open(str(wav),"wb") as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes((pcm*32767).astype("<i2").tobytes())
    background=cv2.imread(str(ROOT/"sample_assets/background/v0830_tokyo_night_fixture.png"));report={"version":"0.8.3.1","visual_approval":"USER REVIEW REQUIRED","candidates":[],"pairwise_iou":{},"recommended_main_3":sorted(BEST)};all_color=[];all_gray=[];best=[];masks={}
    for category,slug,path in CANDIDATES:
        t=load_template(path);features=analyze_pcm(pcm,sr,fps=24,bands=int(t["bands"]),fft_size=2048);engine=AnimationEngine(features,t);renderer=CPURenderer();sampled=[];started=perf_counter()
        def frames():
            for i in range(240):
                frame=renderer.render_rgba(960,160,engine.sample(i/24),t)
                if i in (30,70,110,150,190,225):sampled.append(frame.copy())
                yield frame
        video=OUT/"videos"/(slug+".mp4");encode(video,frames());fps=240/(perf_counter()-started);chosen=sampled[-1];gray=gray_rgba(chosen);mock=screen(background,chosen)
        Image.fromarray(chosen,"RGBA").save(OUT/"previews"/(slug+".png"));Image.fromarray(gray,"RGBA").save(OUT/"grayscale"/(slug+"_grayscale.png"));Image.fromarray(mock,"RGB").save(OUT/"previews"/(slug+"_screen_preview.png"));Image.fromarray(mock,"RGB").save(OUT/"capcut_mockups"/(slug+"_capcut.png"))
        m=metrics(sampled);masks[t["name"]]=chosen[:,:,3]>28;all_color.append((f"{category} · {t['name']}",chosen));all_gray.append((f"{category} · {t['name']}",gray))
        if t["name"] in BEST:best.append((f"{category} · {t['name']}",mock))
        advantages={"Dual":"양쪽 신호의 관계와 중앙 interaction이 명확함","His":"저역 구조감과 차가운 도시 리듬이 선명함","Her":"부드러운 호흡과 pearl/ribbon 잔향이 정지화면에서도 읽힘"}[category]
        concern="사용자 영상의 인물 위치에 따라 vertical placement 미세조정 필요"
        item={"name":t["name"],"category":category,"concept":t["concept_ko"],"geometry":t["signature_variant"],"palette":[t["color"],t["secondary_color"],t["accent_color"],t["highlight_color"]],"bidirectional":m["left_right_balance"]>=.70,"metrics":m,"advantages":advantages,"concerns":concern,"recommended":t["name"] in BEST,"video":str(video),"screen_preview":str(OUT/"previews"/(slug+"_screen_preview.png")),"capcut_mockup":str(OUT/"capcut_mockups"/(slug+"_capcut.png")),"cpu_fps":round(fps,1),"status":"USER REVIEW REQUIRED"}
        report["candidates"].append(item);(OUT/"reports"/(slug+".txt")).write_text(f"{t['name']} ({category})\n{t['concept_ko']}\nGeometry: {t['signature_variant']}\nPalette: {', '.join(item['palette'])}\n좌우 반응: {'PASS' if item['bidirectional'] else 'REWORK'}\n장점: {advantages}\n우려점: {concern}\n미감 승인: USER REVIEW REQUIRED\n",encoding="utf-8")
    names=list(masks)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            inter=np.logical_and(masks[a],masks[b]).sum();union=np.logical_or(masks[a],masks[b]).sum();iou=round(float(inter/max(1,union)),4);report["pairwise_iou"][f"{a} vs {b}"]={"iou":iou,"overly_similar":iou>.72}
    sheet(all_color,OUT/"contact_sheets/ALL_9_CONTACT_SHEET.png",3);sheet(all_gray,OUT/"contact_sheets/ALL_9_GRAYSCALE.png",3);sheet([x for x in all_color if x[0].split(" · ")[1] in BEST],OUT/"contact_sheets/MAIN_3_CONTACT_SHEET.png",3);sheet([x for x in all_gray if x[0].split(" · ")[1] in BEST],OUT/"contact_sheets/MAIN_3_GRAYSCALE.png",3);sheet(best,OUT/"contact_sheets/BEST_3_CAPCUT_MOCKUPS.png",3,585)
    (OUT/"reports/signature_redesign_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["Music Wave Studio v0.8.3.1 Signature Redesign","Visual approval: USER REVIEW REQUIRED",""]
    for x in report["candidates"]:lines += [f"[{x['category']}] {x['name']} {'(RECOMMENDED)' if x['recommended'] else ''}",x["concept"],f"Geometry: {x['geometry']} | Bidirectional: {x['bidirectional']} | Metrics: {x['metrics']}",f"장점: {x['advantages']}",f"우려점: {x['concerns']}",""]
    (OUT/"reports/signature_redesign_report.txt").write_text("\n".join(lines),encoding="utf-8");print(json.dumps({"output":str(OUT),"candidates":len(report["candidates"]),"recommended":sorted(BEST)},ensure_ascii=False))
if __name__=="__main__":main()
