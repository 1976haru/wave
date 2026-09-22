"""Decode audio once and persist frame-aligned features in a content cache."""
from __future__ import annotations
import hashlib, json, shutil, subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable
import numpy as np

@dataclass(frozen=True)
class AnalysisSettings:
    fps: int = 30
    bands: int = 64
    fft_size: int = 4096
    min_frequency: float = 40.0
    max_frequency: float = 18000.0

def decode_audio(path: str | Path, sample_rate: int = 44100) -> tuple[np.ndarray, int]:
    """Decode mono float32, preferring PyAV and falling back to FFmpeg."""
    source = str(Path(path))
    try:
        import av
        chunks = []
        with av.open(source) as container:
            stream = next(s for s in container.streams if s.type == "audio")
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=sample_rate)
            for frame in container.decode(stream):
                converted = resampler.resample(frame)
                for item in converted if isinstance(converted, list) else [converted]:
                    chunks.append(np.asarray(item.to_ndarray(), dtype=np.float32).reshape(-1))
        if chunks:
            return np.concatenate(chunks), sample_rate
    except Exception:
        pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Audio decode failed and FFmpeg was not found on PATH")
    process = subprocess.run([ffmpeg, "-v", "error", "-i", source, "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "pipe:1"], check=True, capture_output=True)
    return np.frombuffer(process.stdout, dtype="<f4").copy(), sample_rate

def _scaled(values, percentile=98.0):
    top = max(float(np.percentile(values, percentile)), 1e-8)
    return np.clip(values / top, 0, 1).astype(np.float32)

def analyze_pcm(x, sr, fps=30, bands=64, fft_size=4096):
    """Calculate all FFT-derived frames up front; rendering only samples this result."""
    samples = np.asarray(x, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 1e-8: samples = samples / peak
    hop = max(1, int(round(sr / fps))); count = max(1, int(np.ceil(len(samples) / hop)))
    padded = np.pad(samples, (fft_size // 2, fft_size + hop)); starts = np.arange(count) * hop
    frames = np.stack([padded[s:s + fft_size] for s in starts])
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    magnitude = np.abs(np.fft.rfft(frames * np.hanning(fft_size), axis=1)).astype(np.float32)
    frequencies = np.fft.rfftfreq(fft_size, 1.0 / sr)
    high_limit = min(float(sr / 2 - 1), 18000.0); edges = np.geomspace(40.0, high_limit, bands + 1)
    spectrum = np.zeros((count, bands), np.float32)
    for band in range(bands):
        mask = (frequencies >= edges[band]) & (frequencies < edges[band + 1])
        if mask.any(): spectrum[:, band] = np.sqrt(np.mean(magnitude[:, mask] ** 2, axis=1) + 1e-12)
    broad = []
    for low, high in ((40, 250), (250, 4000), (4000, min(16000, high_limit))):
        mask = (frequencies >= low) & (frequencies < high)
        broad.append(magnitude[:, mask].mean(axis=1) if mask.any() else np.zeros(count))
    onset = np.maximum(np.diff(magnitude, axis=0, prepend=magnitude[:1]), 0).mean(axis=1)
    spectrum = np.log1p(spectrum); spectrum = np.clip(spectrum / max(float(np.percentile(spectrum, 99)), 1e-8), 0, 1).astype(np.float32)
    return {"spectrum": spectrum, "rms": _scaled(rms), "bass": _scaled(broad[0]), "mid": _scaled(broad[1]), "high": _scaled(broad[2]), "onset": _scaled(onset), "sr": np.array([sr]), "fps": np.array([fps]), "bands": np.array([bands]), "duration": np.array([len(samples) / float(sr)])}

def cache_key(path, settings):
    digest = hashlib.sha256(json.dumps(asdict(settings), sort_keys=True).encode())
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()

def save_cache(path, features):
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); np.savez_compressed(target, **features)

def load_cache(path):
    with np.load(path, allow_pickle=False) as archive: return {key: archive[key] for key in archive.files}

def analyze_file(path, settings=None, cache_dir="cache", logger: Callable[[str], None] | None = None):
    settings = settings or AnalysisSettings(); started = perf_counter(); key = cache_key(path, settings); target = Path(cache_dir) / f"{key}.npz"
    if target.exists():
        result = load_cache(target)
        if logger: logger(f"analysis cache hit key={key[:12]} time={perf_counter()-started:.3f}s")
        return result, True
    pcm, sr = decode_audio(path); result = analyze_pcm(pcm, sr, settings.fps, settings.bands, settings.fft_size); save_cache(target, result)
    if logger: logger(f"analysis cache miss key={key[:12]} time={perf_counter()-started:.3f}s")
    return result, False
