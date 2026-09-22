import numpy as np
def analyze_pcm(x,sr,fps=30,bands=64):
 x=np.asarray(x,dtype=np.float32); x/=max(float(np.max(np.abs(x))) if x.size else 1,1e-8)
 hop=max(1,int(sr/fps)); win=4096; edges=np.geomspace(40,min(18000,sr/2-1),bands+1); freq=np.fft.rfftfreq(win,1/sr)
 n=max(1,int(np.ceil(len(x)/hop))); spec=np.zeros((n,bands),np.float32); rms=np.zeros(n,np.float32); broad=np.zeros((n,3),np.float32); onset=np.zeros(n,np.float32); prev=None
 for i in range(n):
  a=x[i*hop:i*hop+win]
  if len(a)<win:a=np.pad(a,(0,win-len(a)))
  rms[i]=np.sqrt(np.mean(a*a)+1e-12); mag=np.abs(np.fft.rfft(a*np.hanning(win))).astype(np.float32)
  for b in range(bands):
   q=(freq>=edges[b])&(freq<edges[b+1]); spec[i,b]=np.sqrt(np.mean(mag[q]**2)+1e-12) if q.any() else 0
  for j,(lo,hi) in enumerate(((40,250),(250,4000),(4000,16000))):
   q=(freq>=lo)&(freq<hi); broad[i,j]=mag[q].mean() if q.any() else 0
  if prev is not None:onset[i]=np.maximum(mag-prev,0).mean()
  prev=mag
 def sc(a):
  p=max(float(np.percentile(a,98)),1e-8);return np.clip(a/p,0,1).astype(np.float32)
 spec=np.log1p(spec);spec=np.clip(spec/max(float(np.percentile(spec,99)),1e-8),0,1)
 return {"spectrum":spec,"rms":sc(rms),"bass":sc(broad[:,0]),"mid":sc(broad[:,1]),"high":sc(broad[:,2]),"onset":sc(onset),"sr":np.array([sr]),"fps":np.array([fps]),"bands":np.array([bands])}
def save_cache(p,f):np.savez_compressed(p,**f)
def load_cache(p):
 z=np.load(p);return {k:z[k] for k in z.files}
