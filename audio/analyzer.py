"""Versioned, cached audio analysis for render-time sampling."""
from __future__ import annotations
import hashlib,json,logging,os,shutil,subprocess,sys,threading,zipfile
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter
from typing import Callable
import numpy as np
from core.runtime_paths import cache_dir as runtime_cache_dir
from core import memory_mode
ANALYSIS_VERSION="3"
try:
    from scipy import signal as _signal
except ImportError:_signal=None
@dataclass(frozen=True)
class AnalysisSettings:
    fps:int=30;bands:int=64;fft_size:int=4096;min_frequency:float=40.0;max_frequency:float=18000.0
    fft_window:str="hann";spectrum_mapping:str="AUTO";analyzer_backend:str="AUTO"
def _av_chunks(source,sample_rate):
    import av
    with av.open(source) as container:
        stream=next(s for s in container.streams if s.type=="audio");resampler=av.AudioResampler(format="fltp",layout="mono",rate=sample_rate)
        for frame in container.decode(stream):
            converted=resampler.resample(frame)
            for item in converted if isinstance(converted,list) else [converted]:yield np.asarray(item.to_ndarray(),dtype=np.float32).reshape(-1)
def _hidden_kwargs():
    if os.name!="nt":return {}
    return {"creationflags":getattr(subprocess,"CREATE_NO_WINDOW",0)}
def _ffmpeg_chunks(source,sample_rate,block=1<<20):
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:raise RuntimeError("Audio decode failed and FFmpeg was not found. Configure FFmpeg Path in Settings.")
    process=subprocess.Popen([ffmpeg,"-v","error","-i",source,"-f","f32le","-ac","1","-ar",str(sample_rate),"pipe:1"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,**_hidden_kwargs());carry=b""
    try:
        for data in iter(lambda:process.stdout.read(block),b""):
            data=carry+data;usable=len(data)-len(data)%4;carry=data[usable:]
            if usable:yield np.frombuffer(data[:usable],dtype="<f4").copy()
        code=process.wait()
        if code:raise subprocess.CalledProcessError(code,ffmpeg)
    finally:
        if process.poll() is None:process.kill();process.wait()
        process.stdout.close()
def iter_pcm(path:str|Path,sample_rate:int=44100):
    """Yield mono float32 PCM blocks (PyAV, FFmpeg fallback) without holding the whole song."""
    source=str(Path(path));produced=False
    try:
        for chunk in _av_chunks(source,sample_rate):produced=True;yield chunk
        if produced:return
    except Exception:
        if produced:raise
    yield from _ffmpeg_chunks(source,sample_rate)
def decode_audio(path:str|Path,sample_rate:int=44100)->tuple[np.ndarray,int]:
    source=str(Path(path))
    try:
        chunks=list(_av_chunks(source,sample_rate))
        if chunks:return np.concatenate(chunks),sample_rate
    except Exception:pass
    chunks=list(_ffmpeg_chunks(source,sample_rate))
    return (np.concatenate(chunks) if chunks else np.zeros(0,np.float32)),sample_rate
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
ANALYSIS_CHUNK_FRAMES=384
def _frame_block(raw,scale,first,stop,hop,fft_size):
    """Frames [first,stop) of the zero-padded, peak-normalized signal without materializing the whole song."""
    half=fft_size//2;begin=first*hop-half;end=(stop-1)*hop-half+fft_size;segment=np.zeros(end-begin,np.float32);low=max(begin,0);high=min(end,len(raw))
    if high>low:segment[low-begin:high-begin]=raw[low:high]/scale if scale is not None else raw[low:high]
    return np.lib.stride_tricks.sliding_window_view(segment,fft_size)[::hop]
def _raw_stats(raw,hop):
    """Source loudness stats from un-normalized PCM, computed in hop-sized row chunks."""
    if len(raw)<hop:return np.asarray([np.sqrt(np.mean(np.square(raw))+1e-12)]),float(np.sqrt(np.mean(np.square(raw))+1e-12))
    rows=len(raw)//hop;frame_rms=np.empty(rows,np.float32);energy=0.0;step=max(1,(1<<20)//hop)
    for first in range(0,rows,step):
        block=raw[first*hop:min(rows,first+step)*hop].reshape(-1,hop);frame_rms[first:first+len(block)]=np.sqrt(np.mean(np.square(block),axis=1)+1e-12)
    for first in range(0,len(raw),1<<20):energy+=float(np.dot(raw[first:first+(1<<20)].astype(np.float64),raw[first:first+(1<<20)].astype(np.float64)))
    return frame_rms,float(np.sqrt(np.float32(energy/len(raw))+np.float32(1e-12)))
def analyze_pcm(x,sr,fps=30,bands=64,fft_size=4096,fft_window="hann",spectrum_mapping="AUTO",analyzer_backend="AUTO",min_frequency=40.0,max_frequency=18000.0,chunk_frames=None):
    # Chunked STFT: only chunk_frames x fft_size frames/magnitudes exist at a
    # time, so peak memory no longer scales with song length.  Per-frame math
    # is identical to the former whole-song matrix version.
    raw=np.asarray(x,dtype=np.float32).reshape(-1);peak=float(max(raw.max(),-raw.min())) if raw.size else 0.0;scale=peak if peak>1e-8 else None
    use_scipy=analyzer_backend.upper()!="NUMPY" and _signal is not None;resolved="SCIPY" if use_scipy else "NUMPY"
    hop=max(1,int(round(sr/fps)));count=max(1,int(np.ceil(len(raw)/hop)));window=_window(fft_window,fft_size);frequencies=np.fft.rfftfreq(fft_size,1.0/sr)
    high_limit=max(21.0,min(float(sr/2-1),float(max_frequency)));low_limit=max(1.0,min(float(min_frequency),high_limit*.5));edges=_edges(low_limit,high_limit,bands,spectrum_mapping);spectrum=np.zeros((count,bands),np.float32)
    band_masks=[(frequencies>=edges[band])&(frequencies<edges[band+1]) for band in range(bands)]
    defs={"sub":(20,60),"bass_detail":(60,250),"low_mid":(250,500),"mid_detail":(500,2000),"upper_mid":(2000,4000),"high_detail":(4000,8000),"air":(8000,16000)};detail_masks={}
    for name,(low,high) in defs.items():
        upper=min(high,high_limit);mask=(frequencies>=low)&(frequencies<upper);detail_masks[name]=mask if mask.any() and upper>low else None
    detailed={name:np.zeros(count,np.float32) for name in defs};rms=np.empty(count,np.float32);flux=np.empty(count,np.float32);previous=None;chunk=max(2,int(chunk_frames or memory_mode.analysis_chunk_frames()));first=0
    # Single-row FFT calls take a different SIMD path (last-bit float32 drift),
    # so a trailing one-frame remainder is folded into the previous chunk.
    while first<count:
        stop=min(count,first+chunk);stop=count if count-stop==1 else stop;frames=_frame_block(raw,scale,first,stop,hop,fft_size)
        rms[first:stop]=np.sqrt(np.mean(frames*frames,axis=1)+1e-12)
        magnitude=np.abs(np.fft.rfft(frames*window,axis=1)).astype(np.float32);del frames
        for band,mask in enumerate(band_masks):
            if mask.any():spectrum[first:stop,band]=np.sqrt(np.mean(magnitude[:,mask]**2,axis=1)+1e-12)
        for name,mask in detail_masks.items():
            if mask is not None:detailed[name][first:stop]=magnitude[:,mask].mean(axis=1)
        flux[first:stop]=np.maximum(np.diff(magnitude,axis=0,prepend=(magnitude[:1] if previous is None else previous)),0).mean(axis=1);previous=magnitude[-1:].copy();del magnitude;first=stop
    onset=np.maximum(flux-_smooth(flux,use_scipy)*.45,0)
    spectrum=np.log1p(spectrum);spectrum=np.clip(spectrum/max(float(np.percentile(spectrum,99)),1e-8),0,1).astype(np.float32)
    result={name:_scaled(_smooth(value,use_scipy)) for name,value in detailed.items()}
    raw_frame_rms,integrated=_raw_stats(raw,hop)
    raw_db=20*np.log10(np.maximum(raw_frame_rms,1e-7));raw_peak=peak
    deltas=np.diff(raw_frame_rms,prepend=raw_frame_rms[:1]);delta_median=float(np.median(deltas));transient_threshold=delta_median+2.5*float(np.median(np.abs(deltas-delta_median)))
    source_stats={"source_integrated_dbfs":20*np.log10(max(integrated,1e-7)),"source_p20_dbfs":np.percentile(raw_db,20),"source_median_dbfs":np.percentile(raw_db,50),"source_p95_dbfs":np.percentile(raw_db,95),"source_crest_factor":raw_peak/max(integrated,1e-7),"source_dynamic_range_db":np.percentile(raw_db,95)-np.percentile(raw_db,20),"source_silence_ratio":np.mean(raw_db<-48),"source_transient_density":np.mean(deltas>max(transient_threshold,.001))}
    result.update({"spectrum":spectrum,"rms":_scaled(_smooth(rms,use_scipy)),"bass":_scaled(.35*detailed["sub"]+.65*detailed["bass_detail"]),"mid":_scaled(.2*detailed["low_mid"]+.55*detailed["mid_detail"]+.25*detailed["upper_mid"]),"high":_scaled(.7*detailed["high_detail"]+.3*detailed["air"]),"onset":_scaled(onset),"sr":np.array([sr]),"fps":np.array([fps]),"bands":np.array([bands]),"duration":np.array([len(raw)/float(sr)]),"analysis_backend":np.array([resolved]),**{key:np.asarray([value],np.float32) for key,value in source_stats.items()}})
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
def _cache_entry(path,settings,cache_dir=None):
    key=cache_key(path,settings);target=Path(cache_dir or runtime_cache_dir())/f"{key}.npz";return key,target,target.with_suffix(".json"),{"analysis_version":ANALYSIS_VERSION,"settings":asdict(settings)}
def _cache_valid(target,meta_path,expected):
    if not (target.exists() and meta_path.exists()):return None
    try:
        metadata=json.loads(meta_path.read_text(encoding="utf-8"))
        return metadata if metadata.get("analysis_version")==ANALYSIS_VERSION and metadata.get("settings")==expected["settings"] else None
    except (OSError,json.JSONDecodeError,ValueError):return None
_ISOLATED_LOCK=threading.Lock()
WORKER_OK="MWS_ANALYSIS_WORKER_OK"
_ROOT=Path(__file__).resolve().parents[1]
def _worker_command():
    if getattr(sys,"frozen",False):return [sys.executable,"--analysis-worker"]
    return [sys.executable,"-m","audio.analysis_worker"]
def analyze_isolated(path,settings,cache_dir=None,chunk_frames=None,timeout=1800):
    """Analyse one track in a short-lived worker process that only writes the cache.

    Its PCM/FFT heap dies with the process, so the app never keeps NumPy/SciPy
    allocator high-water marks. One worker at a time.
    """
    # Absolute paths: the worker runs with a different cwd, and LOCALAPPDATA/cache paths may be relative.
    command=_worker_command()+[str(Path(path).resolve()),json.dumps(asdict(settings)),str(Path(cache_dir or runtime_cache_dir()).resolve()),str(int(chunk_frames or memory_mode.analysis_chunk_frames()))]
    # A frozen parent leaks PyInstaller bootloader state (_PYI_*/_MEIPASS*) to children; start a clean instance.
    env={key:value for key,value in os.environ.items() if not key.startswith(("_PYI_","_MEIPASS"))}
    env.update(OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1",PYINSTALLER_RESET_ENVIRONMENT="1")
    if not getattr(sys,"frozen",False):env["PYTHONPATH"]=str(_ROOT)+(os.pathsep+env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    with _ISOLATED_LOCK:
        completed=subprocess.run(command,cwd=str(_ROOT),env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=timeout,**_hidden_kwargs())
    detail=completed.stderr.decode("utf-8","replace")
    if completed.returncode or WORKER_OK not in detail:raise RuntimeError(f"analysis worker exit={completed.returncode}: {detail[-400:]!r}")
def analyze_file(path,settings=None,cache_dir=None,logger:Callable[[str],None]|None=None,chunk_frames=None,isolate=None):
    settings=settings or AnalysisSettings();started=perf_counter();key,target,meta_path,expected=_cache_entry(path,settings,cache_dir)
    if _cache_valid(target,meta_path,expected) is not None:
        try:
            result=load_cache(target)
            if logger:logger(f"analysis cache hit key={key[:12]} time={perf_counter()-started:.3f}s")
            return result,True
        except (OSError,ValueError,KeyError,EOFError,zipfile.BadZipFile):pass
    if memory_mode.isolate_analysis() if isolate is None else isolate:
        try:
            analyze_isolated(path,settings,cache_dir,chunk_frames)
            if _cache_valid(target,meta_path,expected) is None:raise RuntimeError("analysis worker wrote no cache")
            result=load_cache(target)
            if logger:logger(f"analysis cache miss (isolated) key={key[:12]} time={perf_counter()-started:.3f}s")
            return result,False
        except Exception:logging.warning("ANALYSIS isolated worker failed; analysing in-process path=%s",path,exc_info=True)
    pcm,sr=decode_audio(path);result=analyze_pcm(pcm,sr,settings.fps,settings.bands,settings.fft_size,settings.fft_window,settings.spectrum_mapping,settings.analyzer_backend,settings.min_frequency,settings.max_frequency,chunk_frames=chunk_frames);del pcm;save_cache(target,result)
    metadata={**expected,"source_hash":key,"sample_rate":sr,"analysis_fps":settings.fps,"bands":settings.bands,"fft_window":settings.fft_window,"spectrum_mapping":settings.spectrum_mapping,"analyzer_backend":str(result["analysis_backend"][0]),"duration":float(result["duration"][0]),"created_timestamp":datetime.now(timezone.utc).isoformat()}
    meta_path.write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding="utf-8")
    if logger:logger(f"analysis cache miss key={key[:12]} time={perf_counter()-started:.3f}s")
    return result,False
def analysis_duration(path,settings=None,cache_dir=None,logger:Callable[[str],None]|None=None)->tuple[float,bool]:
    """Exact analysed duration without keeping features: cached metadata/NPZ key, else analyse once into the cache."""
    settings=settings or AnalysisSettings();_key,target,meta_path,expected=_cache_entry(path,settings,cache_dir);metadata=_cache_valid(target,meta_path,expected)
    if metadata is not None:
        if isinstance(metadata.get("duration"),(int,float)):return float(metadata["duration"]),True
        try:
            with np.load(target,allow_pickle=False) as archive:return float(archive["duration"][0]),True
        except (OSError,ValueError,KeyError,EOFError,zipfile.BadZipFile):pass
    features,hit=analyze_file(path,settings,cache_dir,logger);duration=float(features["duration"][0]);del features
    return duration,hit
def probe_duration(path,settings=None,cache_dir=None,sample_rate=44100)->tuple[float,bool]:
    """SET timeline duration without analysis features: cache metadata, else a streaming sample count.

    The count uses the same decode/resample path as analysis, so it equals the
    analysed duration exactly while holding only one decoded block at a time.
    """
    settings=settings or AnalysisSettings();_key,target,meta_path,expected=_cache_entry(path,settings,cache_dir);metadata=_cache_valid(target,meta_path,expected)
    if metadata is not None and isinstance(metadata.get("duration"),(int,float)):return float(metadata["duration"]),True
    samples=0
    for chunk in iter_pcm(path,sample_rate):samples+=len(chunk)
    return samples/float(sample_rate),False
