import numpy as np,cv2
class CPURenderer:
 def render_rgba(self,w,h,state,t):
  out=np.zeros((h,w,4),np.uint8);layer=np.zeros((h,w,3),np.uint8);v=state["values"];usable=int(w*t.get("width",.72));x0=(w-usable)//2;base={"top":int(h*.2),"center":int(h*.5),"bottom":int(h*.82)}[t.get("position","bottom")];step=usable/len(v);mh=int(h*t.get("height",.22));s=t.get("color","#FFFFFF").lstrip("#");col=(int(s[4:6],16),int(s[2:4],16),int(s[:2],16))
  for i,z in enumerate(v):
   a=int(float(z)*mh);x=int(x0+(i+.5)*step);bw=max(2,int(step*t.get("bar_width",.55)));cv2.rectangle(layer,(x-bw//2,base-a),(x+bw//2,base),col,-1,cv2.LINE_AA)
   if t.get("mirror"):cv2.rectangle(layer,(x-bw//2,base),(x+bw//2,min(h-1,base+a)),col,-1,cv2.LINE_AA)
  if t.get("glow"):layer=cv2.addWeighted(layer,1,cv2.GaussianBlur(layer,(0,0),t.get("glow_radius",10)),.5,0)
  out[:,:,:3]=layer;out[:,:,3]=np.where(cv2.cvtColor(layer,cv2.COLOR_BGR2GRAY)>1,255,0).astype(np.uint8);return out
class GPUBarRenderer:
 def __init__(self):
  import moderngl;self.ctx=moderngl.create_standalone_context()
 def available(self):return self.ctx is not None
