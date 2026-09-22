from __future__ import annotations
import os
class SleepPrevention:
    ES_CONTINUOUS=0x80000000
    ES_SYSTEM_REQUIRED=0x00000001
    ES_DISPLAY_REQUIRED=0x00000002
    def __init__(self,enabled=True):self.enabled=enabled;self.active=False
    def __enter__(self):
        if self.enabled and os.name=="nt":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS|self.ES_SYSTEM_REQUIRED|self.ES_DISPLAY_REQUIRED);self.active=True
            except Exception:self.active=False
        return self
    def __exit__(self,*_):
        if self.active:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            except Exception:pass
            self.active=False
