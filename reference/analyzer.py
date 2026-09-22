from __future__ import annotations
import cv2, numpy as np

def _frame_style(frame,roi=None):
    h,w=frame.shape[:2]; x,y,rw,rh=roi or (0,0,w,h); crop=frame[y:y+rh,x:x+rw]; hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV); saturation=hsv[:,:,1]; value=hsv[:,:,2]; mask=(saturation>35)&(value>45)
    if not mask.any(): mask=value>np.percentile(value,90)
    pixels=crop[mask]; color=pixels.mean(axis=0) if len(pixels) else np.array([255,255,255]); binary=(mask.astype(np.uint8)*255); columns=(binary>0).sum(axis=0); active=np.flatnonzero(columns>max(2,rh*.03)); runs=np.split(active,np.where(np.diff(active)>1)[0]+1) if len(active) else []
    widths=[len(run) for run in runs if len(run)]; gaps=[int(runs[i+1][0]-runs[i][-1]-1) for i in range(len(runs)-1)]
    b,g,r=color; return {"color":f"#{int(r):02X}{int(g):02X}{int(b):02X}","bands":max(1,len(runs)),"bar_width":float(np.median(widths)/max(1,np.median(widths)+(np.median(gaps) if gaps else 1))),"position":"center" if active.size and np.mean(np.where(mask)[0])/rh<.65 else "bottom","height":float(np.ptp(np.where(mask)[0])/rh) if mask.any() else .2,"glow":float(cv2.Laplacian(value,cv2.CV_32F).var())<150}

def analyze_images(paths,roi=None):
    if len(paths)>5: raise ValueError("At most 5 reference images are supported")
    styles=[]
    for path in paths:
        frame=cv2.imread(str(path));
        if frame is None: raise ValueError(f"Cannot read image: {path}")
        styles.append(_frame_style(frame,roi))
    result=dict(styles[0]); result["bands"]=round(np.mean([s["bands"] for s in styles])); result["bar_width"]=float(np.mean([s["bar_width"] for s in styles])); result["height"]=float(np.mean([s["height"] for s in styles])); result["glow"]=sum(bool(s["glow"]) for s in styles)>=len(styles)/2; return result

def analyze_video(path,roi=None,max_seconds=10):
    cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 30; values=[]; previous=None; changes=[]; limit=int(min(max_seconds,10)*fps)
    for index in range(limit):
        ok,frame=cap.read()
        if not ok: break
        if index%max(1,int(fps//5)): continue
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY); values.append(_frame_style(frame,roi))
        if previous is not None: changes.append(float(np.mean(cv2.absdiff(gray,previous)))/255)
        previous=gray
    cap.release()
    if not values: raise ValueError("No video frames could be read")
    movement=float(np.mean(changes)) if changes else 0; result=values[len(values)//2]; result.update({"attack":float(np.clip(.7-movement*2,.15,.7)),"decay":float(np.clip(.95-movement,.7,.95)),"smoothing":float(np.clip(.35-movement,.05,.5)),"animation_speed":movement,"visual_persistence":float(np.clip(1-movement*3,0,1))}); return result
