from __future__ import annotations

import gc,json,shutil,subprocess,sys,wave
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from animation.engine import AnimationEngine
from audio.analyzer import analyze_pcm
from core.memory_telemetry import snapshot
from render.renderer import RendererFactory,release_renderer
from template_system import load_template

OUT=ROOT/"validation_results"/"v0860_morning_shapes_v2"
ORDER=("MORNING_HALO","PEARL_HALO","BREATHING_RING","SOFT_OVAL","HEART_WHISPER","TWIN_HALO","SUNRISE_ARC","VERTICAL_OVAL","ROUND_SQUARE","PEARL_SQUARE","SOFT_DIAMOND","PEARL_HEART","SOFT_CAPSULE","CLOUD_LOOP","PETAL_LOOP","FLOWER_HALO","RIBBON_ORBIT","STEREO_ORBIT","DOTTED_ORBIT","CAFE_FRAME")

def templates():
    by_id={}
    for path in (ROOT/"templates").glob("*.json"):
        data=load_template(path)
        if data.get("category")=="morning_chill_shapes":by_id[data["id"]]=data
    return [by_id[item] for item in ORDER]

def real_background(width,height,variant=0):
    y=np.linspace(0,1,height,dtype=np.float32)[:,None,None];x=np.linspace(0,1,width,dtype=np.float32)[None,:,None]
    palettes=[((188,220,236),(255,235,207)),((178,211,230),(250,244,226)),((231,220,199),(255,247,231)),((193,217,213),(250,232,207))]
    top,bottom=palettes[variant%len(palettes)];image=np.broadcast_to(np.asarray(top)*(1-y)+np.asarray(bottom)*y,(height,width,3)).copy();image*=.94+.06*x
    cv2.rectangle(image,(int(width*.68),0),(int(width*.72),height),(255,248,226),-1);cv2.rectangle(image,(0,int(height*.68)),(width,int(height*.70)),(224,207,183),-1)
    for index in range(5):
        cx=int(width*(.12+index*.18));cy=int(height*(.16+.035*(index%2)));cv2.ellipse(image,(cx,cy),(int(width*.10),int(height*.035)),0,0,360,(245,247,241),-1,cv2.LINE_AA)
    return cv2.GaussianBlur(np.clip(image,0,255).astype(np.uint8),(0,0),5)

def showcase_state(bg=None,phase=.4):
    x=np.linspace(0,np.pi*4,64);values=(.30+.18*np.sin(x+phase)+.09*np.sin(x*2.1-phase)).clip(.06,.72).astype(np.float32)
    result={"values":values,"left_values":np.roll(values,3)*.92,"right_values":np.roll(values,-4)*.78,"rms":.40,"bass":.50,"mid":.35,"high":.20,"onset":.07}
    if bg is not None:result["background_frame"]=bg
    return result

def composite(background,rgba):
    alpha=rgba[:,:,3:4].astype(np.float32)/255
    return np.clip(rgba[:,:,:3]*alpha+background*(1-alpha),0,255).astype(np.uint8)

def contact_sheet(items,path,columns=4,cell_width=480):
    frame_w,frame_h=items[0][1].shape[1],items[0][1].shape[0];image_h=round(cell_width*frame_h/frame_w);cell_h=image_h+30;rows=(len(items)+columns-1)//columns
    canvas=Image.new("RGB",(cell_width*columns,cell_h*rows),(12,15,18));draw=ImageDraw.Draw(canvas)
    for index,(name,array) in enumerate(items):
        x=(index%columns)*cell_width;y=(index//columns)*cell_h;canvas.paste(Image.fromarray(array).resize((cell_width,image_h),Image.Resampling.LANCZOS),(x,y+30));draw.text((x+8,y+8),name,fill=(255,248,236))
    canvas.save(path,quality=95)

def read_audio(path):
    with wave.open(str(path),"rb") as handle:channels=handle.getnchannels();width=handle.getsampwidth();rate=handle.getframerate();raw=handle.readframes(handle.getnframes())
    dtype={1:np.uint8,2:np.int16,4:np.int32}[width];samples=np.frombuffer(raw,dtype=dtype).astype(np.float32)
    samples=(samples-128)/128 if width==1 else samples/float(2**(width*8-1))
    if channels>1:samples=samples.reshape(-1,channels).mean(axis=1)
    return samples,rate

def motion_video(template,target,features,audio_path):
    width,height,fps=1920,1080,24;bg=real_background(width,height,ORDER.index(template["id"]));temporary=target.with_name(target.stem+"_silent.mp4");writer=cv2.VideoWriter(str(temporary),cv2.VideoWriter_fourcc(*"mp4v"),fps,(width,height));renderer=RendererFactory.create("CPU",template);engine=AnimationEngine(features,template)
    for frame_index in range(8*fps):
        state=engine.sample(frame_index/fps);state["background_frame"]=bg;rgba=renderer.render_rgba(width,height,state,dict(template,_quality="BALANCED"));writer.write(cv2.cvtColor(composite(bg,rgba),cv2.COLOR_RGB2BGR))
    writer.release();release_renderer(renderer);ffmpeg=shutil.which("ffmpeg")
    if ffmpeg:subprocess.run([ffmpeg,"-y","-loglevel","error","-i",str(temporary),"-i",str(audio_path),"-t","8","-c:v","copy","-c:a","aac","-shortest",str(target)],check=True);temporary.unlink(missing_ok=True)
    else:temporary.replace(target)

def main():
    OUT.mkdir(parents=True,exist_ok=True);geometry=[];real=[];representative=[];selected={"MORNING_HALO","PEARL_HALO","BREATHING_RING","SOFT_OVAL","HEART_WHISPER"}
    for index,template in enumerate(templates()):
        template=json.loads(json.dumps(template));template["morning_shape"].update({"color_a":"#FFF8EC","opacity":.90,"stroke_style":"THIN","glow_level":"SUBTLE","local_adapt":True})
        renderer=RendererFactory.create("CPU",template);state=showcase_state();rgba=renderer.render_rgba(960,540,state,dict(template,_quality="QUALITY"));geometry.append((template["name"],composite(np.zeros((540,960,3),np.uint8),rgba)))
        bg=real_background(960,540,index);state["background_frame"]=bg;rgba=renderer.render_rgba(960,540,state,dict(template,_quality="QUALITY"));image=composite(bg,rgba);real.append((template["name"],image));release_renderer(renderer)
        if template["id"] in selected:representative.append((template["name"],image))
    contact_sheet(geometry,OUT/"01_geometry_20_contact_sheet.jpg");contact_sheet(real,OUT/"02_real_background_20_contact_sheet.jpg");contact_sheet(representative,OUT/"03_representative_5_real_background.jpg",columns=5,cell_width=384)
    audio_path=ROOT/"sample_assets"/"audio"/"sample_10s.wav";samples,rate=read_audio(audio_path);features=analyze_pcm(samples,rate,fps=24,bands=64)
    filenames={"MORNING_HALO":"04_Morning_Halo_8s.mp4","PEARL_HALO":"05_Pearl_Halo_8s.mp4","BREATHING_RING":"06_Breathing_Ring_8s.mp4","SOFT_OVAL":"07_Soft_Oval_8s.mp4","HEART_WHISPER":"08_Heart_Whisper_8s.mp4"}
    for template in templates():
        if template["id"] in filenames:motion_video(template,OUT/filenames[template["id"]],features,audio_path)
    template=load_template(ROOT/"templates"/"60_morning_halo.json");renderer=RendererFactory.create("CPU",template);rss=[]
    for _set in range(2):
        for track in range(15):frame=renderer.render_rgba(1920,1080,showcase_state(phase=track*.1),dict(template,_quality="PREVIEW"));del frame
        gc.collect();rss.append(snapshot()["rss_mb"])
    release_renderer(renderer);gc.collect();bottom_clear=all(not np.any(item[1][int(item[1].shape[0]*.78):]) for item in geometry)
    report={"templates_total":len(list((ROOT/"templates").glob("*.json"))),"morning_shapes":len(geometry),"legacy_bottom_eq_removed":bottom_clear,"motion_files":len(filenames),"motion_uses_real_audio":True,"memory_rss_after_each_set_mb":rss,"memory_growth_mb":rss[-1]-rss[0],"memory_peak_observed_mb":max(rss),"under_3gb":max(rss)<3072}
    (OUT/"validation_report_v2.json").write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report))

if __name__=="__main__":main()
