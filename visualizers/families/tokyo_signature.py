from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from visualizers.local_background import adaptation_from_metrics, analyze_local_background, derive_underlay_color, smooth_adaptation

SUPPORTED_PARAMETERS = ("variant", "motion", "size", "vertical_position", "horizontal_position", "presence", "auto_adapt", "local_adapt")

MOTION = {"CALM": .72, "STANDARD": .90, "DYNAMIC": 1.08, "VERY_DYNAMIC": 1.25}
MOTION_CEILING = {"CALM": .64, "STANDARD": .78, "DYNAMIC": .91, "VERY_DYNAMIC": 1.0}
PRESENCE = {"SOFT": (.78, .72), "DEFAULT": (.90, .88), "CRISP": (1.0, 1.0)}
VERTICAL = {"TOP": .62, "CENTER": .75, "BOTTOM": .87}
RECOMMENDED = {
    "MIDNIGHT_PULSE": {"motion": "DYNAMIC", "size": 1.0, "vertical_position": "BOTTOM", "presence": "CRISP"},
    "SILK_WAVE": {"motion": "DYNAMIC", "size": 1.0, "vertical_position": "BOTTOM", "presence": "CRISP"},
    "TWO_HEARTS": {"motion": "DYNAMIC", "size": 1.0, "vertical_position": "BOTTOM", "presence": "CRISP"},
}


def _hex(value: str) -> tuple[int, int, int]:
    text = str(value).lstrip("#")
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def resolve_signature_profile(template: dict, width: int, height: int, state: dict | None = None) -> dict:
    settings = template.get("tokyo_signature", {})
    variant = str(settings.get("variant", template.get("signature_variant", "MIDNIGHT_PULSE"))).upper()
    recommended = RECOMMENDED.get(variant, RECOMMENDED["MIDNIGHT_PULSE"])
    motion = str(settings.get("motion", recommended["motion"])).upper()
    presence = str(settings.get("presence", recommended["presence"])).upper()
    size = float(np.clip(settings.get("size", recommended["size"]), .7, 1.3))
    gain = MOTION.get(motion, MOTION["DYNAMIC"]) * size
    if settings.get("auto_adapt", True): gain *= float((state or {}).get("auto_gain", 1.0))
    opacity, contrast = PRESENCE.get(presence, PRESENCE["DEFAULT"])
    horizontal = str(settings.get("horizontal_position", "LEFT")).upper()
    active_width = {"MIDNIGHT_PULSE": 430, "SILK_WAVE": 500, "TWO_HEARTS": 560}.get(variant, 460) * width / 960 * size
    margin = 62 * width / 960
    x0 = margin if horizontal == "LEFT" else ((width-active_width)/2 if horizontal == "CENTER" else width-active_width-margin)
    base = height * VERTICAL.get(str(settings.get("vertical_position", "BOTTOM")).upper(), .87)
    palettes = {
        "MIDNIGHT_PULSE": ["#214CFF", "#745CFF", "#386BFF", "#41D5FF"],
        "SILK_WAVE": ["#FF6FAE", "#FFA6CB", "#CF91FF", "#9FDFFF", "#FFF3FA"],
        "TWO_HEARTS": ["#FF4FA3", "#B77CFF", "#42D9FF", "#FFF0FA"],
    }
    colors = settings.get("colors") or palettes[variant]
    return {"variant":variant,"gain":gain,"ceiling":MOTION_CEILING.get(motion,.91),"opacity":opacity,"contrast":contrast,"size":size,"x0":x0,"active_width":active_width,
            "base":base,"colors":[_hex(color) for color in colors],"local_adapt":bool(settings.get("local_adapt",True))}


def _resample(values, count):
    source=np.asarray(values,np.float32); return np.interp(np.linspace(0,len(source)-1,count),np.arange(len(source)),source)


def signature_geometry(width: int, height: int, state: dict, template: dict) -> dict:
    p=resolve_signature_profile(template,width,height,state); variant=p["variant"]; onset=float(state.get("onset",0)); bass=float(state.get("bass",.4)); mid=float(state.get("mid",.4)); high=float(state.get("high",.3)); energy=float(state.get("energy",state.get("rms",.4)))
    maximum=min(p["base"]-height*.08,height*.68)*p["size"]; dots=[]; lines=[]; bars=[]
    def dot(x,y,r,color,alpha=1):dots.append((float(x),float(y),float(r),color,float(alpha*p["opacity"])))
    def line(points,color,alpha=.8,thickness=1):lines.append((np.asarray(points,np.float32),color,float(alpha*p["opacity"]),int(thickness)))
    if variant=="MIDNIGHT_PULSE":
        count=29; raw=_resample(state["values"],count); weights=np.linspace(1.28,.68,count); shaped=np.power(np.clip(raw*weights*(.82+.32*bass+.22*onset)*p["gain"],0,1),.72)
        shaped=np.minimum(np.convolve(np.pad(shaped,(1,1),mode="edge"),(.18,.64,.18),mode="valid"),p["ceiling"]); xs=np.linspace(p["x0"],p["x0"]+p["active_width"],count); pitch=p["active_width"]/(count-1)
        for i,(x,value) in enumerate(zip(xs,shaped)):
            irregular=.88+.13*math.sin(i*1.71); rise=max(4,value*maximum*irregular); color=p["colors"][min(len(p["colors"])-1,int(i/count*len(p["colors"])))]
            if i%4 in (1,2):
                rows=max(1,int(rise/(6.2*p["size"]))); [dot(x,p["base"]-j*6.2*p["size"],2.0*p["size"],color,.72+.28*j/max(1,rows-1)) for j in range(rows)]
            else: bars.append((x,p["base"],rise,2.2*p["size"],color,.72*p["opacity"]))
        peaks=np.argsort(shaped)[-max(1,min(3,int(1+onset*3))):]
        for i in peaks: dot(xs[i],p["base"]-shaped[i]*maximum-2,2.4*p["size"],p["colors"][-1],.72+.25*onset)
    elif variant=="SILK_WAVE":
        count=46; raw=_resample(state["values"],count); raw*=np.linspace(.78,1.05,count); smooth=raw.copy()
        for _ in range(3):smooth=np.convolve(np.pad(smooth,(2,2),mode="edge"),(.08,.22,.40,.22,.08),mode="valid")
        # Mid/upper-mid energy drives a visible but still soft ribbon.  Two close
        # edges preserve the silk identity without turning it into a thick bar.
        drive=(.58+.62*mid+.30*high+.16*onset)*p["gain"]; rise=np.minimum(np.power(smooth,.74)*drive,p["ceiling"])*maximum*1.04; xs=np.linspace(p["x0"],p["x0"]+p["active_width"],count); ys=p["base"]-rise
        edge=2.3*p["size"]
        line(np.column_stack((xs,ys-edge)),p["colors"][2],.54,max(1,round(1.35*p["size"])))
        line(np.column_stack((xs,ys+edge)),p["colors"][0],.42,1)
        for i in range(1,count,3):dot(xs[i],ys[i],2.25*p["size"],p["colors"][i%4],.88)
        if onset>.28:
            for i in np.argsort(smooth)[-2:]:dot(xs[i],ys[i]-3*p["size"],2.65*p["size"],p["colors"][-1],min(1,.48+onset*.46))
    else:
        half=24; left_raw=_resample(state.get("left_values",state["values"]),half); right_raw=_resample(state.get("right_values",state["values"]),half)
        left=np.convolve(np.pad(left_raw,(2,2),mode="edge"),(.08,.22,.40,.22,.08),mode="valid")*(.60+.58*mid+.18*high)*p["gain"]
        right=np.convolve(np.pad(np.roll(right_raw,2),(1,1),mode="edge"),(.18,.64,.18),mode="valid")*(.62+.58*bass+.12*mid)*p["gain"]
        left=np.minimum(left,p["ceiling"]);right=np.minimum(right,p["ceiling"]);approach=np.clip((onset-.22)/.70,0,1);gap=p["active_width"]*(.18-.105*approach);center=p["x0"]+p["active_width"]/2
        xl=np.linspace(p["x0"],center-gap/2,half);xr=np.linspace(center+gap/2,p["x0"]+p["active_width"],half)
        # A restrained ten-pixel vertical separation and distinct envelopes make
        # the speakers readable as two independent waves even without colour.
        offset=5.0*p["size"];yl=p["base"]-offset-np.clip(left,0,1)*maximum*.84;yr=p["base"]+offset-np.clip(right,0,1)*maximum*.89
        line(np.column_stack((xl,yl)),p["colors"][0],.52,1);line(np.column_stack((xr,yr)),p["colors"][2],.52,1)
        for i in range(0,half,2):dot(xl[i],yl[i],2.0*p["size"],p["colors"][0 if i<half*.65 else 1],.88);dot(xr[i],yr[i],2.0*p["size"],p["colors"][2],.88)
        bridge_alpha=0.0
        if onset>.70:
            bridge_alpha=min(1,(onset-.70)/.24);bridge_y=(yl[-1]+yr[0])/2-3*onset;line([(xl[-1],yl[-1]),(center,bridge_y),(xr[0],yr[0])],p["colors"][1],bridge_alpha*.72,1);dot(center,bridge_y,2.25*p["size"],p["colors"][3],bridge_alpha*.82)
        p["interaction"]={"gap":float(gap),"approach":float(approach),"bridge_alpha":float(bridge_alpha)}
    return {"profile":p,"dots":dots,"lines":lines,"bars":bars,"bounds":(max(0,int(p["x0"]-12)),max(0,int(p["base"]-maximum-12)),min(width,int(p["x0"]+p["active_width"]+12)),min(height,int(p["base"]+12)))}


class TokyoSignatureRenderer:
    name="CPU/TOKYO_SIGNATURE"
    def __init__(self):self._adapt=None;self._frame=0;self.last_local_metrics=None
    def render_rgba(self,width,height,state,template):
        geometry=signature_geometry(width,height,state,template);p=geometry["profile"];local={"underlay_alpha":0.0,"core_alpha_multiplier":1.0,"core_brightness_multiplier":1.0,"core_saturation_multiplier":1.0,"glow_multiplier":1.0}
        background=state.get("background_frame")
        if p["local_adapt"] and background is not None:
            image=np.asarray(background)
            if image.shape[:2]!=(height,width):image=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
            if self._frame%3==0 or self._adapt is None:
                metrics=analyze_local_background(image,geometry["bounds"]);self._adapt=smooth_adaptation(self._adapt,adaptation_from_metrics(metrics));self.last_local_metrics=metrics
            local=self._adapt
        self._frame+=1;rgb=np.zeros((height,width,3),np.float32);alpha=np.zeros((height,width),np.float32);settings=template.get("tokyo_signature",{});stops=[[i/max(1,len(p["colors"])-1),"#%02X%02X%02X"%c] for i,c in enumerate(p["colors"])];under=np.asarray(derive_underlay_color(stops,"CUSTOM"),np.float32)
        def paint_circle(x,y,r,color,a):
            if local["underlay_alpha"]>0:
                cv2.circle(rgb,(round(x),round(y)),max(1,round(r+1.2)),under.tolist(),-1,cv2.LINE_AA);cv2.circle(alpha,(round(x),round(y)),max(1,round(r+1.2)),local["underlay_alpha"]*255,-1,cv2.LINE_AA)
            adjusted=np.asarray(color,np.float32)*local["core_brightness_multiplier"];cv2.circle(rgb,(round(x),round(y)),max(1,round(r)),np.clip(adjusted,0,255).tolist(),-1,cv2.LINE_AA);cv2.circle(alpha,(round(x),round(y)),max(1,round(r)),min(255,a*local["core_alpha_multiplier"]*255),-1,cv2.LINE_AA)
        for x,y,r,c,a in geometry["dots"]:paint_circle(x,y,r,c,a)
        for x,base,rise,thick,c,a in geometry["bars"]:
            cv2.line(rgb,(round(x),round(base)),(round(x),round(base-rise)),c,max(1,round(thick)),cv2.LINE_AA);cv2.line(alpha,(round(x),round(base)),(round(x),round(base-rise)),min(255,a*255),max(1,round(thick)),cv2.LINE_AA)
        for points,c,a,thick in geometry["lines"]:
            pts=np.round(points).astype(np.int32);cv2.polylines(rgb,[pts],False,c,thick,cv2.LINE_AA);cv2.polylines(alpha,[pts],False,min(255,a*255),thick,cv2.LINE_AA)
        glow_strength=.18*local["glow_multiplier"]*PRESENCE.get(str(settings.get("presence","DEFAULT")).upper(),PRESENCE["DEFAULT"])[1]
        glow=cv2.GaussianBlur(rgb,(0,0),2.2);rgb=np.clip(rgb+glow*glow_strength,0,255);alpha=np.clip(alpha+cv2.GaussianBlur(alpha,(0,0),2.0)*.14,0,255)
        return np.dstack((rgb.astype(np.uint8),alpha.astype(np.uint8)))
