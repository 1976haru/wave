from __future__ import annotations
import threading,time
from dataclasses import dataclass
from PySide6.QtCore import QObject,QTimer,Signal,Slot
from preview.engine import PreviewEngine

@dataclass(frozen=True)
class FrameRequest:
    sequence:int;seconds:float;template:dict
class LatestFrameMailbox:
    """Thread-safe single-slot mailbox; a new request replaces any stale request."""
    def __init__(self):self._lock=threading.Lock();self._latest=None;self._sequence=0;self.replaced=0
    def submit(self,seconds,template):
        with self._lock:
            self._sequence+=1
            if self._latest is not None:self.replaced+=1
            self._latest=FrameRequest(self._sequence,float(seconds),dict(template));return self._sequence
    def take(self):
        with self._lock:request=self._latest;self._latest=None;return request
    def clear(self):
        with self._lock:self._latest=None

class PreviewRenderWorker(QObject):
    frameReady=Signal(object,float,object);failed=Signal(str);ready=Signal(str);stopped=Signal()
    def __init__(self,features,template,renderer_choice,mailbox,width=960,height=540,fps=24):
        super().__init__();self.features=features;self.template=dict(template);self.renderer_choice=renderer_choice;self.mailbox=mailbox;self.width=width;self.height=height;self.fps=fps;self.timer=None;self.engine=None;self.running=False
    @Slot()
    def start(self):
        try:
            self.engine=PreviewEngine(self.width,self.height,self.fps,self.renderer_choice);self.engine.features=self.features;self.engine.template=dict(self.template);from render.renderer import RendererFactory;from animation.engine import AnimationEngine;self.engine.renderer=RendererFactory.create(self.renderer_choice,self.engine.template);self.engine.animation=AnimationEngine(self.features,self.template);self.engine.metrics.renderer=self.engine.renderer.name;self.running=True;self.timer=QTimer(self);self.timer.setInterval(1);self.timer.timeout.connect(self.process_latest);self.timer.start();self.ready.emit(self.engine.renderer.name)
        except Exception as exc:self.failed.emit(str(exc));self.stopped.emit()
    @Slot()
    def process_latest(self):
        if not self.running:return
        request=self.mailbox.take()
        if request is None:return
        try:
            self.engine.update_template(dict(request.template,_quality="PREVIEW"));started=time.perf_counter();image=self.engine.frame(request.seconds);elapsed=time.perf_counter()-started;metrics={"sequence":request.sequence,"renderer":self.engine.renderer.name,"fps":1/max(elapsed,1e-9),"replaced":self.mailbox.replaced};self.frameReady.emit(image,request.seconds,metrics)
        except Exception as exc:self.failed.emit(str(exc))
    @Slot()
    def stop(self):
        self.running=False;self.mailbox.clear()
        if self.timer:self.timer.stop()
        self.stopped.emit()

