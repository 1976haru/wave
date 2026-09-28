from __future__ import annotations

import json, subprocess, sys, time
from pathlib import Path

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from animation.engine import AnimationEngine
from audio.analyzer import AnalysisSettings,analyze_file
from core.ffmpeg import resolve_ffmpeg
from template_system import load_template
from visualizers.families.tokyo_signature import TokyoSignatureRenderer,signature_geometry

OUT=ROOT/"validation_results/tokyo_signature_v1";FPS=24;SECONDS=20;FRAMES=FPS*SECONDS
AUDIO=ROOT/"validation_results/v0840_real_world_validation/_chill_actual_28s.wav"
VIDEO=ROOT/"validation_results/v0840_real_world_validation/_chill_background_28s.mp4"
BRIGHT=Path(r"D:\02_시니어 채널\1113_첫눈이 생각나는 감성 올드팝\음원커버 및 썸네일\썸네일 1.png")
CASES=[("midnight_pulse","00_v0850_tokyo_midnight_pulse.json"),("silk_wave","00_v0850_tokyo_silk_wave.json"),("two_hearts","00_v0850_tokyo_two_hearts.json")]

def cover(image,w=1920,h=1080):
    scale=max(w/image.shape[1],h/image.shape[0]);res=cv2.resize(image,(round(image.shape[1]*scale),round(image.shape[0]*scale)),interpolation=cv2.INTER_AREA);x=(res.shape[1]-w)//2;y=(res.shape[0]-h)//2;return res[y:y+h,x:x+w]

def composite(bg,overlay,x=70,y=850):
    out=bg.copy();rgb=overlay[...,:3][...,::-1].astype(np.float32);a=overlay[...,3:4].astype(np.float32)/255;roi=out[y:y+160,x:x+960].astype(np.float32);out[y:y+160,x:x+960]=np.clip(roi*(1-a)+rgb,0,255).astype(np.uint8);return out

def encoder(path,ffmpeg):
    return subprocess.Popen([ffmpeg,"-y","-v","error","-f","rawvideo","-pix_fmt","bgr24","-s","1920x1080","-r",str(FPS),"-i","pipe:0","-i",str(AUDIO),"-t",str(SECONDS),"-shortest","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-c:a","aac",str(path)],stdin=subprocess.PIPE)

def sheet(images,names,path,crop=False):
    tiles=[]
    for image,name in zip(images,names):
        source=image[790:1040,30:1100] if crop else image;tile=cv2.resize(source,(800,450));cv2.rectangle(tile,(0,0),(800,44),(12,14,20),-1);cv2.putText(tile,name,(15,31),cv2.FONT_HERSHEY_SIMPLEX,.72,(250,250,250),2,cv2.LINE_AA);tiles.append(tile)
    cv2.imwrite(str(path),np.hstack(tiles))

def main():
    OUT.mkdir(parents=True,exist_ok=True);ffmpeg=resolve_ffmpeg(None);features,_=analyze_file(AUDIO,AnalysisSettings(fps=FPS,bands=64),OUT/"_cache")
    score=np.asarray(features["rms"][:FRAMES])*.45+np.asarray(features["mid"][:FRAMES])*.35+np.asarray(features["onset"][:FRAMES])*.20;rep_index=int(np.argmax(score));items=[]
    for name,file in CASES:
        template=load_template(ROOT/"templates"/file);items.append({"name":name,"template":template,"engine":AnimationEngine(features,template),"renderer":TokyoSignatureRenderer(),"proc":encoder(OUT/f"{name}.mp4",ffmpeg),"rises":[],"dots":[]})
    capture=cv2.VideoCapture(str(VIDEO));started=time.perf_counter();rep=[];wave=[]
    for index in range(FRAMES):
        ok,bg=capture.read()
        if not ok:capture.set(cv2.CAP_PROP_POS_FRAMES,0);ok,bg=capture.read()
        bg=cover(bg);local=bg[850:1010,70:1030]
        for item in items:
            state=item["engine"].sample(index/FPS);state["background_frame"]=local;overlay=item["renderer"].render_rgba(960,160,state,item["template"]);geo=signature_geometry(960,160,state,item["template"]);ys=[d[1] for d in geo["dots"]]+[float(p[1]) for line in geo["lines"] for p in line[0]]+[b[1]-b[2] for b in geo["bars"]];item["rises"].append(geo["profile"]["base"]-min(ys));item["dots"].append(len(geo["dots"]));composed=composite(bg,overlay);item["proc"].stdin.write(memoryview(composed))
            if index==rep_index:rep.append(composed.copy());wave.append(overlay.copy())
    capture.release();elapsed=time.perf_counter()-started
    for item in items:item["proc"].stdin.close();assert item["proc"].wait()==0
    bright=cover(cv2.imdecode(np.fromfile(BRIGHT,np.uint8),cv2.IMREAD_COLOR));bright_frames=[]
    for item in items:
        engine=AnimationEngine(features,item["template"]);renderer=TokyoSignatureRenderer();overlay=None
        for index in range(rep_index+1):state=engine.sample(index/FPS);state["background_frame"]=bright[850:1010,70:1030];overlay=renderer.render_rgba(960,160,state,item["template"])
        bright_frames.append(composite(bright,overlay))
    names=[name.replace("_"," ").upper() for name,_ in CASES];sheet(rep,names,OUT/"signature_3style_contact_sheet.png");sheet(bright_frames,names,OUT/"signature_bright_contact_sheet.png");black=[composite(np.zeros((1080,1920,3),np.uint8),frame) for frame in wave];sheet(black,names,OUT/"signature_wave_only_contact_sheet.png");sheet(rep,names,OUT/"signature_wave_crop_contact_sheet.png",True)
    metrics={item["name"]:{"median_rise":round(float(np.median(item["rises"])),2),"p90_rise":round(float(np.percentile(item["rises"],90)),2),"max_rise":round(float(np.max(item["rises"])),2),"median_dots":round(float(np.median(item["dots"])),1)} for item in items};fps=round(FRAMES*len(items)/elapsed,2);payload={"version":"0.8.5.0","renderer":"CPU/TOKYO_SIGNATURE","fps":fps,"representative_seconds":round(rep_index/FPS,2),"metrics":metrics,"visual_approval":"USER REVIEW REQUIRED"};(OUT/"validation_report.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8");print(json.dumps(payload,indent=2))
if __name__=="__main__":main()
