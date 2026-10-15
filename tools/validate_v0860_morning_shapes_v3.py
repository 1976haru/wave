from __future__ import annotations

import gc,json,sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.memory_telemetry import snapshot
from render.renderer import RendererFactory,release_renderer
from template_system import load_template
from tools.validate_v0860_morning_shapes import composite,motion_video,read_audio,real_background,showcase_state
from audio.analyzer import analyze_pcm

OUT=ROOT/"validation_results"/"v0860_morning_shapes_v3"
REP=("60_morning_halo.json","61_pearl_halo.json","62_breathing_ring.json","63_soft_oval.json","64_heart_whisper.json")

def green_background(width,height):
    y=np.linspace(0,1,height)[:,None,None];top=np.array([193,220,202]);bottom=np.array([242,231,193]);image=np.broadcast_to(top*(1-y)+bottom*y,(height,width,3)).copy()
    rng=np.random.default_rng(860)
    for _ in range(75):
        center=(int(rng.uniform(0,width)),int(rng.uniform(height*.05,height*.95)));axes=(int(rng.uniform(width*.012,width*.05)),int(rng.uniform(height*.025,height*.10)));color=(int(rng.uniform(118,176)),int(rng.uniform(158,205)),int(rng.uniform(122,165)));cv2.ellipse(image,center,axes,float(rng.uniform(-70,70)),0,360,color,-1,cv2.LINE_AA)
    return cv2.GaussianBlur(np.clip(image,0,255).astype(np.uint8),(0,0),11)

def render(template,bg):
    renderer=RendererFactory.create("CPU",template);state=showcase_state(bg);rgba=renderer.render_rgba(bg.shape[1],bg.shape[0],state,dict(template,_quality="QUALITY"));release_renderer(renderer);return composite(bg,rgba)

def save_sheet(images,path):
    width,height=images[0][1].shape[1],images[0][1].shape[0];thumb_w=384;thumb_h=round(thumb_w*height/width);canvas=Image.new("RGB",(thumb_w*len(images),thumb_h+30),(12,15,18));draw=ImageDraw.Draw(canvas)
    for index,(name,array) in enumerate(images):canvas.paste(Image.fromarray(array).resize((thumb_w,thumb_h),Image.Resampling.LANCZOS),(index*thumb_w,30));draw.text((index*thumb_w+8,8),name,fill=(255,248,236))
    canvas.save(path,quality=95)

def main():
    OUT.mkdir(parents=True,exist_ok=True);width,height=1920,1080;sky=real_background(width,height,0);cafe=real_background(width,height,2);green=green_background(width,height);halo=load_template(ROOT/"templates"/REP[0]);pearl=load_template(ROOT/"templates"/REP[1])
    Image.fromarray(render(halo,sky)).save(OUT/"01_Morning_Halo_sky.jpg",quality=95);Image.fromarray(render(halo,cafe)).save(OUT/"02_Morning_Halo_cafe.jpg",quality=95);Image.fromarray(render(halo,green)).save(OUT/"03_Morning_Halo_green.jpg",quality=95);Image.fromarray(render(pearl,sky)).save(OUT/"04_Pearl_Halo_sky.jpg",quality=95)
    sky_items=[];cafe_items=[]
    for name in REP:
        template=load_template(ROOT/"templates"/name);sky_items.append((template["name"],render(template,sky)));cafe_items.append((template["name"],render(template,cafe)))
    save_sheet(sky_items,OUT/"05_representative_5_sky.jpg");save_sheet(cafe_items,OUT/"06_representative_5_cafe.jpg");save_sheet([("Morning Halo · radial bars",render(halo,sky)),("Pearl Halo · dots",render(pearl,sky))],OUT/"07_Halo_vs_Pearl.jpg")
    audio_path=ROOT/"sample_assets"/"audio"/"sample_10s.wav";samples,rate=read_audio(audio_path);features=analyze_pcm(samples,rate,fps=24,bands=64);motion_video(halo,OUT/"08_Morning_Halo_8s.mp4",features,audio_path);motion_video(pearl,OUT/"09_Pearl_Halo_8s.mp4",features,audio_path)
    renderer=RendererFactory.create("CPU",halo);rss=[]
    for _set in range(2):
        for track in range(15):frame=renderer.render_rgba(width,height,showcase_state(phase=track*.1),dict(halo,_quality="PREVIEW"));del frame
        gc.collect();rss.append(snapshot()["rss_mb"])
    release_renderer(renderer);diameter=float(np.ptp(__import__("visualizers.families.morning_shape",fromlist=["shape_geometry"]).shape_geometry(width,height,showcase_state(),halo)["base_points"],axis=0)[0]);report={"morning_halo_diameter_px":diameter,"morning_halo_opacity":halo["morning_shape"]["opacity"],"pearl_halo_opacity":pearl["morning_shape"]["opacity"],"default_y":halo["morning_shape"]["position_y"],"three_backgrounds":True,"halo_primitive":"radial_bars","pearl_primitive":"dots","memory_rss_after_each_set_mb":rss,"memory_peak_mb":max(rss),"set_growth_mb":rss[-1]-rss[0],"under_300mb":max(rss)<300}
    (OUT/"validation_report_v3.json").write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report))

if __name__=="__main__":main()
