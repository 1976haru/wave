from __future__ import annotations

import gc
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from core.memory_telemetry import snapshot
from render.renderer import RendererFactory, release_renderer
from template_system import load_template

OUT=ROOT/"validation_results"/"v0860_morning_shapes"


def templates():
    result=[]
    for path in (ROOT/"templates").glob("*.json"):
        data=load_template(path)
        if data.get("category")=="morning_chill_shapes":result.append(data)
    return sorted(result,key=lambda item:int(next(path.name[:2] for path in (ROOT/"templates").glob("*.json") if load_template(path).get("id")==item["id"])))


def background(width,height):
    source=cv2.imread(str(ROOT/"resources"/"smoke_reference.png"))
    if source is not None:return cv2.cvtColor(cv2.resize(source,(width,height)),cv2.COLOR_BGR2RGB)
    y=np.linspace(0,1,height)[:,None,None];a=np.array([244,218,190])[None,None,:];b=np.array([151,190,207])[None,None,:]
    return np.broadcast_to(a*(1-y)+b*y,(height,width,3)).astype(np.uint8).copy()


def state(phase=.3,bg=None):
    x=np.linspace(0,np.pi*4,64);values=(.28+.22*np.sin(x+phase)+.12*np.sin(x*2.3-phase)).clip(.05,.75).astype(np.float32)
    data={"values":values,"left_values":np.roll(values,2),"right_values":np.roll(values,-3),"rms":.38,"bass":.48,"mid":.34,"high":.22,"onset":.08}
    if bg is not None:data["background_frame"]=bg
    return data


def composite(bg,rgba):
    alpha=rgba[:,:,3:4].astype(np.float32)/255
    return np.clip(rgba[:,:,:3]*alpha+bg*(1-alpha),0,255).astype(np.uint8)


def sheet(items,path,columns=4,cell=(480,300)):
    cw,ch=cell;rows=(len(items)+columns-1)//columns;canvas=Image.new("RGB",(cw*columns,ch*rows),(20,24,28));draw=ImageDraw.Draw(canvas)
    for index,(name,image) in enumerate(items):
        tile=Image.fromarray(image).resize((cw,ch));x=(index%columns)*cw;y=(index//columns)*ch;canvas.paste(tile,(x,y));draw.rectangle((x,y,x+cw,y+28),fill=(12,15,18));draw.text((x+9,y+7),name,fill=(255,248,236))
    canvas.save(path,quality=94)


def main():
    OUT.mkdir(parents=True,exist_ok=True);all_items=[];representative=[];bg=background(960,540)
    for template in templates():
        renderer=RendererFactory.create("CPU",template)
        rgba=renderer.render_rgba(960,540,state(.45,bg),dict(template,_quality="QUALITY"));release_renderer(renderer)
        image=composite(bg,rgba);all_items.append((template["name"],image))
        if template["id"] in {"MORNING_HALO","PEARL_HALO","BREATHING_RING","SOFT_OVAL","HEART_WHISPER"}:representative.append((template["name"],image))
    sheet(all_items,OUT/"morning_shapes_20_contact_sheet.jpg",4)
    sheet(representative,OUT/"morning_shapes_representative_5.jpg",5,(384,360))
    # 1080p and bounded-memory smoke: 15 tracks x 2 sets, renderer retained just
    # as the production SET path does while per-frame arrays are released.
    template=load_template(ROOT/"templates"/"60_morning_halo.json");renderer=RendererFactory.create("CPU",template);rss=[]
    for set_index in range(2):
        for track in range(15):
            frame=renderer.render_rgba(1920,1080,state(track*.1),dict(template,_quality="PREVIEW"));assert frame.shape==(1080,1920,4);del frame
        gc.collect();rss.append(snapshot()["rss_mb"]*2**20)
    release_renderer(renderer);gc.collect()
    report={"templates_total":len(list((ROOT/"templates").glob("*.json"))),"morning_shapes":len(all_items),"representative_shapes":len(representative),"memory_rss_after_each_set_bytes":rss,"memory_growth_bytes":rss[-1]-rss[0],"memory_peak_observed_bytes":max(rss),"under_3gb":max(rss)<3_000_000_000}
    (OUT/"validation_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))


if __name__=="__main__":main()
