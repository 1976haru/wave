from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class TimingMetrics:
    rendered_frames:int=0;dropped_frames:int=0;max_drift:float=0.0;started_at:float|None=None;last_render_wall:float|None=None
    def average_fps(self,now):return self.rendered_frames/max(1e-9,now-self.started_at) if self.started_at is not None else 0.0

class FrameScheduler:
    """Audio-frame-index scheduler. Late indices are dropped, never queued."""
    def __init__(self,fps=24):self.fps=float(fps);self.interval=1/self.fps;self.metrics=TimingMetrics();self.last_audio_time=None;self.last_frame_index=-1
    def reset(self,audio_time=0.0,wall_time=None):
        audio_time=max(0,float(audio_time));self.metrics=TimingMetrics(started_at=wall_time);self.last_audio_time=audio_time;self.last_frame_index=math.floor(audio_time*self.fps)-1
    def seek(self,audio_time,wall_time=None):self.reset(audio_time,wall_time)
    def should_render(self,audio_time,wall_time):
        audio_time=max(0,float(audio_time))
        if self.metrics.started_at is None:self.reset(audio_time,wall_time)
        if self.last_audio_time is not None and audio_time+0.002<self.last_audio_time:self.seek(audio_time,wall_time)
        self.last_audio_time=audio_time;frame_index=math.floor(audio_time*self.fps)
        if frame_index<=self.last_frame_index:return False
        skipped=max(0,frame_index-self.last_frame_index-1);self.metrics.dropped_frames+=skipped;scheduled_time=frame_index/self.fps;self.metrics.max_drift=max(self.metrics.max_drift,max(0,audio_time-scheduled_time));self.last_frame_index=frame_index;self.metrics.rendered_frames+=1;self.metrics.last_render_wall=wall_time;return True
