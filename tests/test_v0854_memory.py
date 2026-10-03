"""v0.8.5.4 real-world memory stability: chunked analysis, one-track SET loading, deterministic cleanup."""
import gc
import json
import logging
import sys
import tracemalloc
import wave
import weakref
from pathlib import Path

import numpy as np
import pytest

from audio import analyzer
from audio.analyzer import AnalysisSettings, analysis_duration, analyze_file, analyze_pcm


# --------------------------------------------------------------------------
# Reference: the v0.8.5.3 whole-song FFT analyzer, kept verbatim for equivalence.
def legacy_analyze_pcm(x, sr, fps=30, bands=64, fft_size=4096, fft_window="hann", spectrum_mapping="AUTO", analyzer_backend="AUTO", min_frequency=40.0, max_frequency=18000.0):
    _signal, _window, _edges, _smooth, _scaled = analyzer._signal, analyzer._window, analyzer._edges, analyzer._smooth, analyzer._scaled
    samples=np.asarray(x,dtype=np.float32).reshape(-1);raw_samples=samples.copy();peak=float(np.max(np.abs(samples))) if samples.size else 0.0
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
    raw_frame_rms=np.sqrt(np.mean(np.square(raw_samples[:len(raw_samples)//hop*hop].reshape(-1,hop)),axis=1)+1e-12) if len(raw_samples)>=hop else np.asarray([np.sqrt(np.mean(np.square(raw_samples))+1e-12)])
    raw_db=20*np.log10(np.maximum(raw_frame_rms,1e-7));integrated=float(np.sqrt(np.mean(np.square(raw_samples))+1e-12));raw_peak=float(np.max(np.abs(raw_samples))) if raw_samples.size else 0.0
    deltas=np.diff(raw_frame_rms,prepend=raw_frame_rms[:1]);delta_median=float(np.median(deltas));transient_threshold=delta_median+2.5*float(np.median(np.abs(deltas-delta_median)))
    source_stats={"source_integrated_dbfs":20*np.log10(max(integrated,1e-7)),"source_p20_dbfs":np.percentile(raw_db,20),"source_median_dbfs":np.percentile(raw_db,50),"source_p95_dbfs":np.percentile(raw_db,95),"source_crest_factor":raw_peak/max(integrated,1e-7),"source_dynamic_range_db":np.percentile(raw_db,95)-np.percentile(raw_db,20),"source_silence_ratio":np.mean(raw_db<-48),"source_transient_density":np.mean(deltas>max(transient_threshold,.001))}
    result.update({"spectrum":spectrum,"rms":_scaled(_smooth(rms,use_scipy)),"bass":_scaled(.35*detailed["sub"]+.65*detailed["bass_detail"]),"mid":_scaled(.2*detailed["low_mid"]+.55*detailed["mid_detail"]+.25*detailed["upper_mid"]),"high":_scaled(.7*detailed["high_detail"]+.3*detailed["air"]),"onset":_scaled(onset),"sr":np.array([sr]),"fps":np.array([fps]),"bands":np.array([bands]),"duration":np.array([len(samples)/float(sr)]),"analysis_backend":np.array([resolved]),**{key:np.asarray([value],np.float32) for key,value in source_stats.items()}})
    return result


# Visual features must be bit-identical; loudness stats only differ by float64 accumulation.
VISUAL_KEYS = ("spectrum", "rms", "bass", "mid", "high", "onset", "sub", "bass_detail", "low_mid", "mid_detail", "upper_mid", "high_detail", "air")
STAT_TOLERANCE = 1e-4


def _music_like(seconds, sr=44100, seed=0):
    rng = np.random.default_rng(seed); t = np.arange(int(seconds * sr)) / sr
    kick = np.sin(2*np.pi*55*t) * np.exp(-((t % .5) * 18)); chord = .3*np.sin(2*np.pi*220*t) + .2*np.sin(2*np.pi*330*t*(1+.002*np.sin(t)))
    hat = rng.normal(0, .08, t.size) * (np.sin(2*np.pi*8*t) > .7); swell = .5 + .5*np.sin(2*np.pi*t/7)
    return ((kick + chord*swell + hat) * .4).astype(np.float32)


def assert_equivalent(old, new):
    assert old.keys() == new.keys()
    for key in old:
        assert old[key].shape == new[key].shape and old[key].dtype == new[key].dtype, key
    for key in VISUAL_KEYS:
        assert np.array_equal(old[key], new[key]), key
    assert float(old["duration"][0]) == float(new["duration"][0])
    for key in old:
        if key.startswith("source_"):
            assert abs(float(old[key][0]) - float(new[key][0])) <= STAT_TOLERANCE, key


@pytest.mark.parametrize("seconds,sr,fps,bands,fft_size", [(12.3, 44100, 30, 64, 4096), (9.0, 48000, 24, 96, 4096), (5.1, 22050, 30, 32, 2048), (.05, 8000, 24, 16, 512)])
def test_chunked_analyzer_matches_whole_song_fft(seconds, sr, fps, bands, fft_size):
    pcm = _music_like(seconds, sr)
    old = legacy_analyze_pcm(pcm, sr, fps=fps, bands=bands, fft_size=fft_size)
    for chunk in (1, 2, 7, 384, 10**6):
        assert_equivalent(old, analyze_pcm(pcm, sr, fps=fps, bands=bands, fft_size=fft_size, chunk_frames=chunk))


@pytest.mark.parametrize("frames", [385, 769, 384, 2, 1])
def test_chunk_remainders_stay_bit_exact(frames):
    sr, fps = 44100, 30; hop = sr // fps
    pcm = _music_like(frames * hop / sr, sr, seed=frames)[: (frames - 1) * hop + 1]
    old = legacy_analyze_pcm(pcm, sr, fps=fps)
    assert old["spectrum"].shape[0] == frames
    assert_equivalent(old, analyze_pcm(pcm, sr, fps=fps))


def test_chunked_analyzer_silence_and_numpy_backend():
    silent = np.zeros(44100 * 3, np.float32)
    assert_equivalent(legacy_analyze_pcm(silent, 44100), analyze_pcm(silent, 44100))
    pcm = _music_like(4, seed=3)
    assert_equivalent(legacy_analyze_pcm(pcm, 44100, analyzer_backend="NUMPY"), analyze_pcm(pcm, 44100, analyzer_backend="NUMPY"))


def test_chunked_analyzer_does_not_mutate_input():
    pcm = _music_like(3); before = pcm.copy()
    analyze_pcm(pcm, 44100)
    assert np.array_equal(pcm, before)


REAL_AUDIO = sorted(Path("D:/suno/업로드/ja02").glob("*.wav"))[:2] if Path("D:/suno/업로드/ja02").is_dir() else []


@pytest.mark.skipif(not REAL_AUDIO, reason="representative user WAVs not available")
@pytest.mark.parametrize("path", REAL_AUDIO, ids=lambda p: p.stem)
def test_chunked_analyzer_matches_on_real_wav(path):
    pcm, sr = analyzer.decode_audio(path)
    assert_equivalent(legacy_analyze_pcm(pcm, sr, fps=30), analyze_pcm(pcm, sr, fps=30))


def test_long_audio_analyzer_peak_memory_is_bounded():
    # 10 minutes @ 44.1kHz: the whole-song version allocated >1.5GB here.
    pcm = _music_like(600, seed=7); gc.collect()
    tracemalloc.start()
    try:
        features = analyze_pcm(pcm, 44100, fps=30)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert features["spectrum"].shape == (18000, 64)
    assert peak < 160 * 2**20, f"analysis peak {peak / 2**20:.1f}MB"


# --------------------------------------------------------------------------
# SET renderer lifecycle with a fake FFmpeg process.
class FakeStream:
    def __init__(self, data=b""): self.closed = False; self.written = 0; self._lines = [data] if data else []
    def write(self, chunk): self.written += len(chunk)
    def readline(self): return self._lines.pop(0) if self._lines else b""
    def close(self): self.closed = True


class FakeProcess:
    instances = []
    def __init__(self, command, **_kwargs):
        self.command = command; self.stdin = FakeStream(); self.stderr = FakeStream(); self.returncode = None; self.terminated = False
        Path(command[-1]).write_bytes(b"partial"); FakeProcess.instances.append(self)
    def poll(self): return self.returncode
    def wait(self, timeout=None):
        if self.returncode is None: self.returncode = -15 if self.terminated else 0
        return self.returncode
    def terminate(self): self.terminated = True
    def kill(self): self.terminated = True


class Tracked(dict):
    __hash__ = object.__hash__


def _write_wav(path, seconds, sr=8000, freq=220.0):
    data = (np.sin(2*np.pi*freq*np.arange(int(seconds*sr))/sr) * 12000).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(sr); handle.writeframes(data.tobytes())
    return path


@pytest.fixture
def set_env(monkeypatch, tmp_path):
    import pipeline.set_renderer as set_renderer
    from pipeline.exporter import ExportOptions
    from template_system import load_template
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    FakeProcess.instances = []
    monkeypatch.setattr(set_renderer.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(set_renderer, "resolve_ffmpeg", lambda _path=None: "ffmpeg")
    stats = {"engines": weakref.WeakSet(), "features": weakref.WeakSet(), "max_engines": 0, "max_features": 0, "loads": 0, "released": 0, "renderers": []}
    real_engine, real_analyze = set_renderer.AnimationEngine, set_renderer.analyze_file

    class CountingEngine(real_engine):
        def __init__(self, features, template):
            super().__init__(features, template); stats["engines"].add(self)
            stats["max_engines"] = max(stats["max_engines"], len(stats["engines"])); stats["max_features"] = max(stats["max_features"], len(stats["features"]))

    def counting_analyze(path, settings=None, cache_dir=None, logger=None):
        features, hit = real_analyze(path, settings, cache_dir, logger); tracked = Tracked(features)
        stats["features"].add(tracked); stats["loads"] += 1
        return tracked, hit

    class FakeRenderer:
        name = "FAKE"
        def __init__(self): self.released = False; self.calls = 0; self.fail_at = stats.get("fail_at")
        def render_rgba(self, w, h, state, template):
            self.calls += 1
            if self.fail_at is not None and self.calls >= self.fail_at: raise RuntimeError("renderer boom")
            return np.zeros((h, w, 4), np.uint8)
        def release(self): self.released = True; stats["released"] += 1

    def make_renderer(_choice, _template=None):
        renderer = FakeRenderer(); stats["renderers"].append(renderer); return renderer

    monkeypatch.setattr(set_renderer, "AnimationEngine", CountingEngine)
    monkeypatch.setattr(set_renderer, "analyze_file", counting_analyze)
    monkeypatch.setattr(set_renderer.RendererFactory, "create", staticmethod(make_renderer))
    files = [_write_wav(tmp_path / f"track-{i:02d}.wav", .6 + .1*(i % 3), freq=110 + 40*i) for i in range(6)]
    template = load_template("templates/00_v0850_tokyo_silk_wave.json")
    options = ExportOptions(width=96, height=32, fps=10, quality="PREVIEW", renderer="CPU", format="mp4", include_audio=False)
    return set_renderer, files, template, options, stats, tmp_path


def test_set_holds_one_active_track_and_engine(set_env):
    set_renderer, files, template, options, stats, tmp_path = set_env
    result = set_renderer.render_set(files, tmp_path / "out.mp4", template, options, timeline_path=tmp_path / "timeline.json")
    assert result["tracks"] == len(files)
    assert stats["loads"] == len(files)
    assert stats["max_engines"] == 1 and stats["max_features"] == 1
    gc.collect()
    assert len(stats["engines"]) == 0 and len(stats["features"]) == 0
    assert stats["released"] == 1 and FakeProcess.instances[0].stdin.closed
    timeline = json.loads((tmp_path / "timeline.json").read_text(encoding="utf-8"))
    assert [t["duration"] for t in timeline["tracks"]] == [pytest.approx(analysis_duration(f, AnalysisSettings(fps=10, bands=int(template.get("bands", 64))))[0]) for f in files]


def test_set_cancel_releases_everything(set_env):
    set_renderer, files, template, options, stats, tmp_path = set_env
    calls = {"n": 0}
    def cancel():
        calls["n"] += 1; return calls["n"] > len(files) + 15
    with pytest.raises(InterruptedError):
        set_renderer.render_set(files, tmp_path / "out.mp4", template, options, cancel=cancel)
    process = FakeProcess.instances[0]
    assert process.terminated and process.stdin.closed and stats["released"] == 1
    assert not (tmp_path / "out.mp4").exists()
    gc.collect(); assert len(stats["engines"]) == 0 and len(stats["features"]) == 0


def test_set_exception_releases_everything(set_env):
    set_renderer, files, template, options, stats, tmp_path = set_env
    stats["fail_at"] = 12
    with pytest.raises(RuntimeError, match="renderer boom"):
        set_renderer.render_set(files, tmp_path / "out.mp4", template, options)
    assert FakeProcess.instances[0].terminated and stats["released"] == 1
    assert not (tmp_path / "out.mp4").exists()
    gc.collect(); assert len(stats["engines"]) == 0 and len(stats["features"]) == 0


def test_set_closes_background_source(set_env, monkeypatch):
    set_renderer, files, template, options, stats, tmp_path = set_env
    closed = []
    class Source:
        def frame(self, *_args): return None
        def close(self): closed.append(True)
    monkeypatch.setattr(set_renderer, "source_from_template", lambda _template: Source())
    set_renderer.render_set(files[:2], tmp_path / "out.mp4", template, options)
    assert closed == [True]


def test_set_progress_is_throttled_and_logs_memory(set_env, caplog):
    set_renderer, files, template, options, stats, tmp_path = set_env
    events = []
    with caplog.at_level(logging.INFO):
        result = set_renderer.render_set(files, tmp_path / "out.mp4", template, options, progress_detail=events.append)
    frame_events = [e for e in events if "set_track_index" in e]
    assert frame_events[-1]["percent"] == pytest.approx(100.0)
    assert len(frame_events) < result["frames"]
    stages = [r.getMessage().split()[1] for r in caplog.records if r.getMessage().startswith("MEMORY stage=")]
    assert stages[0] == "stage=set_start" and stages[-1] == "stage=set_end"
    assert stages.count("stage=track_start") == len(files) and stages.count("stage=track_end") == len(files)


def test_analysis_duration_uses_cache_without_features(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    path = _write_wav(tmp_path / "a.wav", 1.25); settings = AnalysisSettings(fps=24)
    duration, hit = analysis_duration(path, settings)
    assert duration == pytest.approx(1.25, abs=.01) and hit is False
    monkeypatch.setattr(analyzer, "load_cache", lambda *_: pytest.fail("full NPZ load not expected"))
    monkeypatch.setattr(analyzer, "decode_audio", lambda *_: pytest.fail("decode not expected"))
    assert analysis_duration(path, settings) == (duration, True)


def test_corrupt_cache_is_reanalysed(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    path = _write_wav(tmp_path / "a.wav", .5); settings = AnalysisSettings(fps=24)
    analyze_file(path, settings)
    for npz in (tmp_path / "local").rglob("*.npz"): npz.write_bytes(b"not a zip")
    features, hit = analyze_file(path, settings)
    assert hit is False and features["spectrum"].shape[0] == 12


# --------------------------------------------------------------------------
def test_renderer_caches_are_bounded():
    from render import renderer
    from visualizers.families import soft_round_led
    for cached in (renderer._gradient_lut, soft_round_led._color_lut, soft_round_led._sprite, soft_round_led._underlay_sprite):
        assert cached.cache_info().maxsize is not None and cached.cache_info().maxsize <= 256


def test_adaptive_renderer_releases_gpu_context():
    psutil = pytest.importorskip("psutil")
    pytest.importorskip("moderngl")
    from render.renderer import RendererFactory, release_renderer
    from template_system import load_template
    template = load_template("templates/23_chill_ribbon.json"); process = psutil.Process()
    def cycle():
        renderer = RendererFactory.create("AUTO", template); release_renderer(renderer); del renderer; gc.collect()
    cycle(); cycle()
    handles, private = process.num_handles(), process.memory_info().private
    for _ in range(5): cycle()
    assert process.num_handles() - handles <= 10
    assert process.memory_info().private - private < 40 * 2**20


def test_release_renderer_is_safe_for_any_object():
    from render.renderer import CPURenderer, release_renderer
    release_renderer(None); release_renderer(CPURenderer()); release_renderer(object())


def test_preview_engine_release_drops_references(tmp_path):
    from preview.engine import PreviewEngine
    engine = PreviewEngine(); closed = []
    class Source:
        def close(self): closed.append(True)
    engine.features = {"x": np.zeros(3)}; engine.background_source = Source(); engine.animation = object()
    engine.release()
    assert engine.features is None and engine.animation is None and engine.renderer is None and closed == [True]


# --------------------------------------------------------------------------
def test_memory_telemetry_logs_checkpoint(caplog):
    from core import memory_telemetry
    with caplog.at_level(logging.INFO):
        data = memory_telemetry.checkpoint("unit_test", track=3)
    message = [r.getMessage() for r in caplog.records if r.getMessage().startswith("MEMORY stage=unit_test")][0]
    assert "rss_mb=" in message and "private_mb=" in message and "handles=" in message and "track=3" in message
    if sys.platform == "win32": assert data["private_mb"] and data["handles"]


def test_memory_telemetry_low_memory_warning(monkeypatch, caplog):
    from core import memory_telemetry
    monkeypatch.setenv("MWS_LOW_MEMORY_MB", str(10**9))
    with caplog.at_level(logging.WARNING):
        data = memory_telemetry.checkpoint("low")
    assert data["low_memory"] and memory_telemetry.low_memory_message(data)
    assert any("MEMORY low_available" in r.getMessage() for r in caplog.records)


def test_memory_telemetry_without_psutil(monkeypatch):
    from core import memory_telemetry
    monkeypatch.setattr(memory_telemetry, "_psutil", None)
    data = memory_telemetry.snapshot()
    assert set(data) >= {"rss_mb", "private_mb", "handles", "threads", "available_mb"}
    if sys.platform == "win32": assert data["private_mb"] > 0 and data["available_mb"] > 0


def test_app_caps_native_blas_threads():
    source = Path("app.py").read_text(encoding="utf-8")
    cap = source.index("OPENBLAS_NUM_THREADS"); first_numpy = source.index("import numpy")
    assert cap < first_numpy
    assert source.index("OPENBLAS_NUM_THREADS") < source.index("from core.version import")


def test_memory_watch_script_is_locale_independent():
    script = Path("tools/memory_watch.ps1").read_text(encoding="utf-8")
    assert "InvariantCulture" in script and "{0:N1}" not in script and "FfmpegWorkingSetMB" in script


# --------------------------------------------------------------------------
# Real FFmpeg: four SETs back-to-back must not grow threads/handles/private memory.
def test_four_sets_thread_handle_memory_baseline(tmp_path, monkeypatch):
    psutil = pytest.importorskip("psutil")
    from core.ffmpeg import resolve_ffmpeg
    if not resolve_ffmpeg(None): pytest.skip("FFmpeg not available")
    from pipeline.exporter import ExportOptions
    from pipeline.set_renderer import render_set
    from template_system import load_template
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    template = load_template("templates/00_v0850_tokyo_silk_wave.json")
    options = ExportOptions(width=320, height=64, fps=12, quality="PREVIEW", renderer="AUTO", format="mp4", include_audio=False)
    process = psutil.Process(); ends = []
    for set_index in range(4):
        folder = tmp_path / f"set{set_index}"; folder.mkdir()
        files = [_write_wav(folder / f"{i:02d}.wav", 1.0, sr=22050, freq=90 + 25*i + set_index) for i in range(15)]
        render_set(files, tmp_path / f"set{set_index}.mp4", template, options)
        gc.collect(); ends.append((process.memory_info().private, process.num_handles(), process.num_threads()))
    assert ends[-1][0] - ends[0][0] < 60 * 2**20, ends
    assert ends[-1][1] - ends[0][1] <= 20, ends
    assert ends[-1][2] - ends[0][2] <= 2, ends
    assert not [c for c in process.children(recursive=True) if "ffmpeg" in c.name().lower()]


# --------------------------------------------------------------------------
# Queue completion must run on the GUI thread (PySide6 runs lambda slots on the worker thread).
def test_queue_completion_runs_on_gui_thread(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path)); monkeypatch.setenv("MWS_AUTO_CLOSE_MS", "1")
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    from mws_queue.queue_manager import JobSet
    from ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([]); window = MainWindow(safe_mode=True); gui = QThread.currentThread(); seen = {}
    original_completion, original_progress = window._queue_completion, window._task_progress
    def completion(result):
        seen["completion_on_gui"] = QThread.currentThread() is gui; original_completion(result)
    def progress(value, total):
        seen["progress_on_gui"] = QThread.currentThread() is gui; original_progress(value, total)
    monkeypatch.setattr(window, "_queue_completion", completion)
    window.queue_manager.state_path = tmp_path / "queue.json"; window.queue_manager.sets = []
    window.queue_manager.add(JobSet("gui-thread", [{"audio": str(tmp_path / "a.wav")}], output_dir=str(tmp_path / "out")))
    import ui.main_window as main_window
    monkeypatch.setattr(main_window, "render_audio", lambda *args, **kwargs: {})
    window.total_progress.valueChanged.connect(lambda _value: seen.setdefault("progress_on_gui", QThread.currentThread() is gui))
    assert window.start_task("queue", (window.queue_manager, False))
    deadline = __import__("time").time() + 20
    while "completion_on_gui" not in seen and __import__("time").time() < deadline: app.processEvents()
    while window.thread is not None and __import__("time").time() < deadline: app.processEvents()
    assert seen.get("completion_on_gui") is True
    assert seen.get("progress_on_gui") is True
    assert window.thread is None and window.worker is None
    window.close(); app.processEvents()


def test_main_window_does_not_connect_worker_signals_to_lambdas():
    source = Path("ui/main_window.py").read_text(encoding="utf-8")
    for signal in ("worker.done", "worker.completed", "worker.progress", "worker.stage_changed", "worker.cancelled", "worker.ready", "thread.finished"):
        assert f"{signal}.connect(lambda" not in source, signal
