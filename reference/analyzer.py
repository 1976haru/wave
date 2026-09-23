from __future__ import annotations
import cv2, numpy as np

def _crop(frame,roi):
    h,w=frame.shape[:2]
    if roi is None:return frame
    x,y,rw,rh=map(int,roi)
    if rw<=0 or rh<=0 or x<0 or y<0 or x+rw>w or y+rh>h: raise ValueError("ROI is outside the reference frame")
    return frame[y:y+rh,x:x+rw]
def _runs(active): return [part for part in np.split(active,np.where(np.diff(active)>1)[0]+1) if len(part)] if len(active) else []
def _frame_style(frame,roi=None):
    crop=_crop(frame,roi); h,w=crop.shape[:2]; hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV); saturation,value=hsv[:,:,1],hsv[:,:,2]; mask=(saturation>35)&(value>45)
    if mask.mean()>.55 or not mask.any(): mask=value>np.percentile(value,90)
    pixels=crop[mask]; color=np.median(pixels,axis=0) if len(pixels) else np.array([255,255,255]); columns=mask.sum(axis=0); active=np.flatnonzero(columns>max(2,h*.03)); runs=_runs(active); widths=[len(run) for run in runs]; gaps=[runs[i+1][0]-runs[i][-1]-1 for i in range(len(runs)-1)]; ys=np.where(mask)[0]; center=float(ys.mean()/h) if ys.size else .8; upper=mask[:h//2].sum(); lower=mask[h//2:].sum(); symmetry=1-abs(float(upper-lower))/max(1,float(upper+lower)); bw=float(np.median(widths)) if widths else 2; gap=float(np.median(gaps)) if gaps else bw
    b,g,r=color; continuity=float(np.clip(len(runs)/max(8.0,w/18.0),0,1));occupancy=float(np.clip(mask.mean()*4,0,1));confidence=float(np.clip(0.55*continuity+0.45*occupancy,0,1)); return {"color":f"#{int(r):02X}{int(g):02X}{int(b):02X}","gradient_start":f"#{int(r):02X}{int(g):02X}{int(b):02X}","confidence":confidence,"bands":int(np.clip(len(runs),8,256)),"bar_width":float(np.clip(bw/max(1,bw+gap),.05,1)),"gap":float(np.clip(gap/max(1,bw+gap),0,.95)),"position":"top" if center<.35 else "center" if center<.65 else "bottom","height":float(np.clip(np.ptp(ys)/h if ys.size else .2,.05,.9)),"glow":bool(cv2.Laplacian(value,cv2.CV_32F).var()<180),"glow_strength":float(np.clip(1-cv2.Laplacian(value,cv2.CV_32F).var()/500,0,1)),"mirror":bool(symmetry>.82)}
def analyze_images(paths,roi=None):
    if not paths: raise ValueError("Add at least one reference image")
    if len(paths)>5: raise ValueError("At most 5 reference images are supported")
    styles=[]
    for path in paths:
        frame=cv2.imread(str(path));
        if frame is None: raise ValueError(f"Cannot read image: {path}")
        styles.append(_frame_style(frame,roi))
    result=dict(styles[0])
    for key in ("bands","bar_width","gap","height","glow_strength"): result[key]=float(np.mean([s[key] for s in styles]))
    result["bands"]=int(round(result["bands"])); result["glow"]=sum(s["glow"] for s in styles)>=len(styles)/2; result["mirror"]=sum(s["mirror"] for s in styles)>=len(styles)/2; return result
def analyze_video(path,roi=None,max_seconds=10):
    seconds=float(np.clip(max_seconds,5,10)); cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 30; sampled=[]; energies=[]; previous=None; limit=int(seconds*fps); stride=max(1,int(fps/10))
    for index in range(limit):
        ok,frame=cap.read()
        if not ok:break
        if index%stride:continue
        crop=_crop(frame,roi); gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY); sampled.append(_frame_style(frame,roi))
        if previous is not None: energies.append(float(np.mean(cv2.absdiff(gray,previous)))/255)
        previous=gray
    cap.release()
    if not sampled:raise ValueError("No video frames could be read")
    movement=float(np.percentile(energies,75)) if energies else 0; variability=float(np.std(energies)) if energies else 0; result=dict(sampled[len(sampled)//2]); result.update({"motion_speed":movement,"animation_speed":movement,"attack":float(np.clip(.72-movement*3.5,.12,.7)),"decay":float(np.clip(.96-movement*1.4,.68,.96)),"smoothing":float(np.clip(.42-movement*2,.04,.5)),"visual_persistence":float(np.clip(.95-movement*2.5-variability,0,1))}); return result
