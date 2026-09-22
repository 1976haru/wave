"""Versioned, cached audio analysis for render-time sampling."""
from __future__ import annotations
import hashlib,json,shutil,subprocess
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter
from typing import Callable
import numpy as np
ANALYSIS_VERSION="2"
try:
    from scipy import signal as _signal
except ImportError:_signal=None
@dataclass(frozen=True)
class AnalysisSettings:
    fps:int=30;bands:int=64;fft_size:int=4096;min_frequency:float=40.0;max_frequency:float=18000.0
    fft_window:str="hann";spectrum_mapping:str="AUTO";analyzer_backend:str="AUTO"
def decode_audio(path:str|Path,sample_rate:int=44100)->tuple[np.ndarray,int]:
    source=str(Path(path))
    try:
        import av
        chunks=[]
        with av.open(source) as container:
            stream=next(s for s in container.streams if s.type=="audio");resampler=av.AudioResampler(format="fltp",layout="mono",rate=sample_rate)
            for frame in container.decode(stream):
                converted=resampler.resample(frame)
                for item in converted if isinstance(converted,list) else [converted]:chunks.append(np.asarray(item.to_ndarray(),dtype=np.float32).reshape(-1))
        if chunks:return np.concatenate(chunks),sample_rate
    except Exception:pass
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:raise RuntimeError("Audio decode failed and FFmpeg was not found. Configure FFmpeg Path in Settings.")
    process=subprocess.run([ffmpeg,"-v","error","-i",source,"-f","f32le","-ac","1","-ar",str(sample_rate),"pipe:1"],check=True,capture_output=True)
    return np.frombuffer(process.stdout,dtype="<f4").copy(),sample_rate
def _scaled(values,percentile=98.0):
    values=np.asarray(values,dtype=np.float32);top=max(float(np.percentile(values,percentile)),1e-8)
    return np.clip(values/top,0,1).astype(np.float32)
def _window(name,size):
    name=name.lower()
    if name not in {"hann","hamming","blackman"}:raise ValueError(f"Unsupported FFT window: {name}")
    if _signal is not None:return _signal.get_window(name,size,fftbins=True).astype(np.float32)
    return {"hann":np.hanning,"hamming":np.hamming,"blackman":np.blackman}[name](size).astype(np.float32)
def _edges(low,high,count,mapping):
    mapping=mapping.upper().replace("MEL-LIKE","PERCEPTUAL")
    if mapping=="AUTO":mapping="PERCEPTUAL"
    if mapping=="LOG":return np.geomspace(low,high,count+1)
    if mapping!="PERCEPTUAL":raise ValueError(f"Unsupported spectrum mapping: {mapping}")
    hz_to_mel=lambda hz:2595.0*np.log10(1.0+hz/700.0);mel_to_hz=lambda mel:700.0*(10.0**(mel/2595.0)-1.0)
    return mel_to_hz(np.linspace(hz_to_mel(low),hz_to_mel(high),count+1))
def _smooth(values,use_scipy):
    if len(values)<5:return np.asarray(values,dtype=np.float32)
    if use_scipy:
        sos=_signal.butter(2,.34,output="sos")
        try:return _signal.sosfiltfilt(sos,values).astype(np.float32)
        except ValueError:return _signal.sosfilt(sos,values).astype(np.float32)
    return np.convolve(values,np.ones(3,np.float32)/3.0,mode="same").astype(np.float32)
def analyze_pcm(x,sr,fps=30,bands=64,fft_size=4096,fft_window="hann",spectrum_mapping="AUTO",analyzer_backend="AUTO",min_frequency=40.0,max_frequency=18000.0):
    samples=np.asarray(x,dtype=np.float32).reshape(-1);peak=float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak>1e-8:samples=samples/peak
    use_scipy=analyzer_backend.upper()!="NUMPY" and _signal is not None;resolved="SCIPY" if use_scipy else "NUMPY"
    hop=max(1,int(round(sr/fps)));count=max(1,int(np.ceil(len(samples)/hop)));padded=np.pad(samples,(fft_size//2,fft_size+hop));starts=np.arange(count)*hop
    frames=np.stack([padded[s:s+fft_size] for s in starts]);rms=np.sqrt(np.mean(frames*frames,axis=1)+1e-12)
    magnitude=np.abs(np.fft.rfft(frames*_window(fft_window,fft_size),axis=1)).astype(np.float32);frequencies=np.fft.rfftfreq(fft_size,1.0/sr)
    high_limit=max(21.0,min(float(sr/2-1),float(max_frequency)));low_limit=max(1.0,min(float(min_frequency),high_limit*.5));edges=_edges(low_limit,high_limit,bands,spectrum_mapping);spectrum=np.zeros((count,bands),np.float32)
    for band in range(bands):
        mask=(frequencies>=edges[band])&(frequencies<edges[band+1])
        if mask.any():spectrum[:,band]=np.sqrt(np.mean(magnitude[:,mask]**2,axis=1)+1e-12)
    defs={"sub":(20,60),"bass_detail":(60,250),"low_mid":(250,500),"mid_detail":(500,2000),"upper_mid":(2000,4000),"high_detail":(4000,8000),"air":(8000,16000)};detailed={}
    for name,(low,high) in defs.items():
        upper=min(high,high_limit);mask=(frequencies>=low)&(frequencies<upper);detailed[name]=magnitude[:,mask].mean(axis=1) if mask.any() and upper>low else np.zeros(count,np.float32)
    flux=np.maximum(np.diff(magnitude,axis=0,prepend=magnitude[:1]),0).mean(axis=1);onset=np.maximum(flux-_smooth(flux,use_scipy)*.45,0)
    spectrum=np.log1p(spectrum);spectrum=np.clip(spectrum/max(float(np.percentile(spectrum,99)),1e-8),0,1).astype(np.float32)
    result={name:_scaled(_smooth(value,use_scipy)) for name,value in detailed.items()}
    result.update({"spectrum":spectrum,"rms":_scaled(_smooth(rms,use_scipy)),"bass":_scaled(.35*detailed["sub"]+.65*detailed["bass_detail"]),"mid":_scaled(.2*detailed["low_mid"]+.55*detailed["mid_detail"]+.25*detailed["upper_mid"]),"high":_scaled(.7*detailed["high_detail"]+.3*detailed["air"]),"onset":_scaled(onset),"sr":np.array([sr]),"fps":np.array([fps]),"bands":np.array([bands]),"duration":np.array([len(samples)/float(sr)]),"analysis_backend":np.array([resolved])})
    return result
def cache_key(path,settings):
    payload={"analysis_version":ANALYSIS_VERSION,"settings":asdict(settings)};digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode())
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()
def save_cache(path,features):
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(target,**features)
def load_cache(path):
    with np.load(path,allow_pickle=False) as archive:return {key:archive[key] for key in archive.files}
def analyze_file(path,settings=None,cache_dir="cache",logger:Callable[[str],None]|None=None):
    settings=settings or AnalysisSettings();started=perf_counter();key=cache_key(path,settings);target=Path(cache_dir)/f"{key}.npz";meta_path=target.with_suffix(".json");expected={"analysis_version":ANALYSIS_VERSION,"settings":asdict(settings)}
    if target.exists() and meta_path.exists():
        try:
            metadata=json.loads(meta_path.read_text(encoding="utf-8"))
            if metadata.get("analysis_version")==ANALYSIS_VERSION and metadata.get("settings")==expected["settings"]:
                result=load_cache(target)
                if logger:logger(f"analysis cache hit key={key[:12]} time={perf_counter()-started:.3f}s")
                return result,True
        except (OSError,json.JSONDecodeError,ValueError):pass
    pcm,sr=decode_audio(path);result=analyze_pcm(pcm,sr,settings.fps,settings.bands,settings.fft_size,settings.fft_window,settings.spectrum_mapping,settings.analyzer_backend,settings.min_frequency,settings.max_frequency);save_cache(target,result)
    metadata={**expected,"source_hash":key,"sample_rate":sr,"analysis_fps":settings.fps,"bands":settings.bands,"fft_window":settings.fft_window,"spectrum_mapping":settings.spectrum_mapping,"analyzer_backend":str(result["analysis_backend"][0]),"created_timestamp":datetime.now(timezone.utc).isoformat()}
    meta_path.write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding="utf-8")
    if logger:logger(f"analysis cache miss key={key[:12]} time={perf_counter()-started:.3f}s")
    return result,False
