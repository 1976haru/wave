import numpy as np
class AnimationEngine:
 def __init__(self,features,template):self.f=features;self.t=template;self.prev=None
 def sample(self,seconds):
  fps=float(self.f["fps"][0]);i=min(len(self.f["spectrum"])-1,max(0,int(seconds*fps)));v=self.f["spectrum"][i].copy()
  v=np.clip(v*float(self.t.get("response",1.25))*(.65+.35*float(self.f["rms"][i]))+float(self.f["onset"][i])*self.t.get("onset_boost",.1),0,1)
  if self.prev is None:self.prev=v
  else:
   k=np.where(v>self.prev,float(self.t.get("attack",.45)),float(self.t.get("decay",.86)));self.prev=k*self.prev+(1-k)*v
  return {"values":self.prev.copy(),"bass":float(self.f["bass"][i]),"mid":float(self.f["mid"][i]),"high":float(self.f["high"][i]),"onset":float(self.f["onset"][i])}
