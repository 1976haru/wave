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

OUT=ROOT/"validation_results/tokyo_signature_v1_1";FPS=24;SECONDS=20;FRAMES=FPS*SECONDS
AUDIO=ROOT/"validation_results/v0840_real_world_validation/_chill_actual_28s.wav"
CASES=[("midnight_pulse_v11","00_v0850_tokyo_midnight_pulse.json"),("silk_wave_v11","00_v0850_tokyo_silk_wave.json"),("two_hearts_v11","00_v0850_tokyo_two_hearts.json")]

def clean_background(index,bright=False):
    h,w=1080,1920;y,x=np.mgrid[0:h,0:w];phase=index/FPS
    if bright:
        top=np.array([230,218,210],np.float32);bottom=np.array([188,198,218],np.float32)
    else:
        top=np.array([62,42,66],np.float32);bottom=np.array([18,28,49],np.float32)
    mix=(y/(h-1))[...,None];image=top*(1-mix)+bottom*mix
    # Soft window/city bokeh only: no text, subtitle, line or visualizer.
    for cx,cy,r,color in ((300,260,190,(120,80,150)),(1450,340,250,(45,95,155)),(1040,780,310,(95,48,90))):
        glow=np.exp(-((x-cx)**2+(y-cy)**2)/(2*r*r))[...,None];image+=glow*np.asarray(color,np.float32)*(.10+.015*np.sin(phase*.25+cx))
    image=np.clip(image,0,255).astype(np.uint8)
    cv2.rectangle(image,(0,900),(1920,1080),(20,24,36) if not bright else (174,181,196),-1)
    return image

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
    rms=np.asarray(features["rms"][:FRAMES]);mid=np.asarray(features["mid"][:FRAMES]);onset=np.asarray(features["onset"][:FRAMES]);score=rms*.42+mid*.38+onset*.20;rep_index=int(np.argmax(score));items=[]
    for name,file in CASES:
        template=load_template(ROOT/"templates"/file);items.append({"name":name,"template":template,"engine":AnimationEngine(features,template),"renderer":TokyoSignatureRenderer(),"proc":encoder(OUT/f"{name}.mp4",ffmpeg),"rises":[],"dots":[],"frames":{}})
    sequence={"quiet":int(np.argmin(score)),"normal":int(np.argmin(np.abs(score-np.median(score)))),"onset":int(np.argmin(np.abs(onset-np.percentile(onset,85)))),"strong onset":int(np.argmax(onset)),"release":min(FRAMES-1,int(np.argmax(onset))+8)}
    started=time.perf_counter();rep=[];wave=[];dark_background=clean_background(0)
    for index in range(FRAMES):
        bg=dark_background
        for item in items:
            state=item["engine"].sample(index/FPS);state["background_frame"]=bg[850:1010,70:1030];overlay=item["renderer"].render_rgba(960,160,state,item["template"]);geo=signature_geometry(960,160,state,item["template"]);ys=[d[1] for d in geo["dots"]]+[float(point[1]) for line in geo["lines"] for point in line[0]]+[bar[1]-bar[2] for bar in geo["bars"]];item["rises"].append(geo["profile"]["base"]-min(ys));item["dots"].append(len(geo["dots"]));composed=composite(bg,overlay);item["proc"].stdin.write(memoryview(composed))
            if index==rep_index:rep.append(composed.copy());wave.append(overlay.copy())
            if item["name"]=="two_hearts_v11" and index in sequence.values():item["frames"][index]=composed.copy()
    elapsed=time.perf_counter()-started
    for item in items:item["proc"].stdin.close();assert item["proc"].wait()==0
    bright_frames=[]
    for item in items:
        engine=AnimationEngine(features,item["template"]);renderer=TokyoSignatureRenderer();overlay=None;bright=clean_background(rep_index,True)
        for index in range(rep_index+1):state=engine.sample(index/FPS);state["background_frame"]=bright[850:1010,70:1030];overlay=renderer.render_rgba(960,160,state,item["template"])
        bright_frames.append(composite(bright,overlay))
    names=["MIDNIGHT PULSE","SILK WAVE","TWO HEARTS"];sheet(rep,names,OUT/"signature_v11_3style_contact_sheet.png");sheet(bright_frames,names,OUT/"signature_v11_bright_contact_sheet.png");sheet([composite(np.zeros((1080,1920,3),np.uint8),frame) for frame in wave],names,OUT/"signature_v11_wave_only_contact_sheet.png");sheet(rep,names,OUT/"signature_v11_wave_crop_contact_sheet.png",True)
    heart=items[2];ordered=[heart["frames"][sequence[label]] for label in sequence];tiles=[]
    for label,image in zip(sequence,ordered):
        tile=cv2.resize(image[780:1040,30:1100],(640,360));cv2.rectangle(tile,(0,0),(640,42),(12,14,20),-1);cv2.putText(tile,label.upper(),(14,29),cv2.FONT_HERSHEY_SIMPLEX,.66,(250,250,250),2,cv2.LINE_AA);tiles.append(tile)
    cv2.imwrite(str(OUT/"two_hearts_interaction_sequence.png"),np.hstack(tiles))
    metrics={item["name"]:{"median_rise":round(float(np.median(item["rises"])),2),"p90_rise":round(float(np.percentile(item["rises"],90)),2),"max_rise":round(float(np.max(item["rises"])),2),"median_dots":round(float(np.median(item["dots"])),1)} for item in items};payload={"version":"0.8.5.0-dev","source":"generated clean background without text/subtitle/visualizer","renderer":"CPU/TOKYO_SIGNATURE","fps":round(FRAMES*len(items)/elapsed,2),"representative_seconds":round(rep_index/FPS,2),"interaction_seconds":{key:round(value/FPS,2) for key,value in sequence.items()},"metrics":metrics,"visual_approval":"USER FINAL VISUAL REVIEW REQUIRED"};(OUT/"validation_report.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8");print(json.dumps(payload,indent=2))

if __name__=="__main__":main()
