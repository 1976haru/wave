from __future__ import annotations

class FFmpegProgressParser:
    """Parse key=value progress output emitted by ffmpeg -progress."""
    def __init__(self, duration_seconds: float):
        self.duration_seconds=max(float(duration_seconds), 1e-9)
        self.values={}
    def feed(self, line: str):
        line=line.strip()
        if not line or "=" not in line:return None
        key,value=line.split("=",1); self.values[key]=value
        if key not in {"out_time_ms","progress"}:return None
        raw=self.values.get("out_time_ms", "0")
        try: out_ms=max(0,int(raw))
        except ValueError: out_ms=0
        event={"out_time_ms":out_ms,"out_time":out_ms/1_000_000.0,"percent":min(100.0,max(0.0,out_ms/1_000_000.0/self.duration_seconds*100.0)),"frame":self._number("frame"),"fps":self._float("fps"),"speed":self.values.get("speed","")}
        if key=="progress" and value=="end":event["percent"]=100.0;event["done"]=True
        return event
    def _number(self,key):
        try:return int(float(self.values.get(key,0)))
        except (TypeError,ValueError):return 0
    def _float(self,key):
        try:return float(self.values.get(key,0))
        except (TypeError,ValueError):return 0.0
