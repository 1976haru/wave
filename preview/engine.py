from __future__ import annotations
from dataclasses import dataclass
from time import perf_counter
from audio.analyzer import AnalysisSettings, analyze_file
from animation.engine import AnimationEngine
from render.renderer import RendererFactory

def format_time(seconds):
    value=max(0,int(seconds)); return f"{value//60:02d}:{value%60:02d}"

@dataclass
class PreviewMetrics:
    renderer:str=""; cache_hit:bool=False; analysis_seconds:float=0; fps:float=0

class PreviewEngine:
    """Low-resolution cached, frame-at-time preview; never writes a temporary video."""
    def __init__(self,width=960,height=540,fps=24,renderer="AUTO"):
        self.width,self.height,self.fps=width,height,fps; self.renderer_choice=renderer; self.features=None; self.animation=None; self.renderer=None; self.template={}; self.last_time=-1.0; self.metrics=PreviewMetrics()
    @property
    def duration(self): return float(self.features["duration"][0]) if self.features is not None else 0.0
    def load(self,audio_path,template,cache_dir="cache"):
        started=perf_counter(); self.template=dict(template); self.features,hit=analyze_file(audio_path,AnalysisSettings(fps=self.fps,bands=int(template.get("bands",64))),cache_dir); self.renderer=RendererFactory.create(self.renderer_choice); self.animation=AnimationEngine(self.features,self.template); self.last_time=-1; self.metrics=PreviewMetrics(self.renderer.name,hit,perf_counter()-started,0); return self.metrics
    def update_template(self,template):
        requested=int(template.get("bands",64)); current=int(self.features["spectrum"].shape[1]) if self.features is not None else requested; self.template=dict(template)
        if self.features is not None:
            if requested!=current:
                import numpy as np
                source=self.features["spectrum"]; old=np.linspace(0,1,current); new=np.linspace(0,1,requested); self.features=dict(self.features); self.features["spectrum"]=np.stack([np.interp(new,old,row) for row in source]).astype(np.float32); self.features["bands"]=np.array([requested])
            self.animation=AnimationEngine(self.features,self.template); self.last_time=-1
        return requested!=current
    def seek(self,seconds):
        self.last_time=float(seconds);
        if self.animation is not None:self.animation.reset()
    def frame(self,seconds):
        if self.animation is None: raise RuntimeError("Preview audio is not loaded")
        seconds=max(0,min(float(seconds),self.duration));
        if seconds<self.last_time: self.animation.reset()
        started=perf_counter(); state=self.animation.sample(seconds); image=self.renderer.render_rgba(self.width,self.height,state,self.template); elapsed=perf_counter()-started; instant=1/max(elapsed,1e-6); self.metrics.fps=instant if not self.metrics.fps else self.metrics.fps*.8+instant*.2; self.last_time=seconds; return image
