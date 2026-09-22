import numpy as np
from audio.analyzer import analyze_pcm
from animation.engine import AnimationEngine
def test_engine():
 sr=44100;t=np.arange(sr)/sr;x=np.sin(2*np.pi*110*t);f=analyze_pcm(x,sr,bands=32);s=AnimationEngine(f,{}).sample(.3);assert len(s["values"])==32
