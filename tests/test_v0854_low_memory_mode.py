"""v0.8.5.4 memory saver mode: probe, chunk profile, isolated analysis, SET boundary guard."""
from __future__ import annotations
import wave
from pathlib import Path

import numpy as np
import pytest

import audio.analyzer as analyzer
from audio.analyzer import AnalysisSettings, analyze_file, analyze_pcm, probe_duration
from core import memory_mode
from mws_queue.queue_manager import JobSet, QueueManager


def _write_wav(path, seconds, sr=8000, freq=220.0):
    data = (np.sin(2*np.pi*freq*np.arange(int(seconds*sr))/sr) * 12000).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(sr); handle.writeframes(data.tobytes())
    return path


@pytest.fixture
def saver(monkeypatch):
    previous = memory_mode.is_enabled()
    def set_mode(value): memory_mode.set_enabled(value)
    yield set_mode
    memory_mode.set_enabled(previous)


def test_profile_follows_mode(saver):
    saver(True)
    assert memory_mode.analysis_chunk_frames() == 128 and memory_mode.isolate_analysis()
    saver(False)
    assert 256 <= memory_mode.analysis_chunk_frames() <= 512 and not memory_mode.isolate_analysis()


def test_low_memory_chunk_is_bit_identical_to_normal_chunk():
    rng = np.random.default_rng(3); sr = 22050
    pcm = (np.sin(2*np.pi*180*np.arange(sr*7)/sr) * .4 + rng.normal(0, .05, sr*7)).astype(np.float32)
    low = analyze_pcm(pcm, sr, fps=30, chunk_frames=128); normal = analyze_pcm(pcm, sr, fps=30, chunk_frames=384)
    assert low.keys() == normal.keys()
    for key in low: np.testing.assert_array_equal(low[key], normal[key], err_msg=key)


def test_probe_duration_matches_analysis_without_features(tmp_path, monkeypatch):
    path = _write_wav(tmp_path / "a.wav", 2.37); settings = AnalysisSettings(fps=24)
    monkeypatch.setattr(analyzer, "analyze_pcm", lambda *a, **k: pytest.fail("probe must not analyse"))
    duration, hit = probe_duration(path, settings, tmp_path / "cache")
    assert hit is False and not (tmp_path / "cache").exists()
    monkeypatch.undo()
    features, _ = analyze_file(path, settings, tmp_path / "cache", isolate=False)
    assert duration == float(features["duration"][0])
    monkeypatch.setattr(analyzer, "iter_pcm", lambda *a, **k: pytest.fail("cache metadata expected"))
    assert probe_duration(path, settings, tmp_path / "cache") == (duration, True)


def test_isolated_analysis_runs_in_worker_and_matches(tmp_path, monkeypatch):
    path = _write_wav(tmp_path / "b.wav", 1.6, freq=330.0); settings = AnalysisSettings(fps=24, bands=32)
    reference, _ = analyze_file(path, settings, tmp_path / "in_process", isolate=False)
    monkeypatch.setattr(analyzer, "analyze_pcm", lambda *a, **k: pytest.fail("analysis must run in the worker process"))
    isolated, hit = analyze_file(path, settings, tmp_path / "isolated", isolate=True)
    assert hit is False and list((tmp_path / "isolated").glob("*.npz"))
    for key in reference: np.testing.assert_array_equal(reference[key], isolated[key], err_msg=key)
    assert memory_mode.live_ffmpeg_children() == []


def test_isolated_analysis_with_relative_cache_dir(tmp_path, monkeypatch):
    # The worker runs with another cwd; a relative LOCALAPPDATA/cache path must still land where the app looks.
    monkeypatch.chdir(tmp_path); _write_wav(tmp_path / "r.wav", .7)
    monkeypatch.setattr(analyzer, "analyze_pcm", lambda *a, **k: pytest.fail("analysis must run in the worker process"))
    features, hit = analyze_file("r.wav", AnalysisSettings(fps=24), "rel_cache", isolate=True)
    assert hit is False and list((tmp_path / "rel_cache").glob("*.npz")) and features["spectrum"].shape[1] == 64


def test_isolated_analysis_failure_falls_back_in_process(tmp_path, monkeypatch, caplog):
    path = _write_wav(tmp_path / "c.wav", .8)
    import sys
    monkeypatch.setattr(analyzer, "_worker_command", lambda: [sys.executable, "-c", "raise SystemExit(3)"])
    features, hit = analyze_file(path, AnalysisSettings(fps=24), tmp_path / "cache", isolate=True)
    assert hit is False and features["spectrum"].shape[1] == 64
    assert "isolated worker failed" in caplog.text


def test_worker_exit_zero_without_marker_is_a_failure(tmp_path, monkeypatch):
    # A frozen exe that starts as the GUI (e.g. single-instance exit) returns 0 without analysing.
    import sys
    monkeypatch.setattr(analyzer, "_worker_command", lambda: [sys.executable, "-c", "pass"])
    with pytest.raises(RuntimeError, match="analysis worker"):
        analyzer.analyze_isolated(_write_wav(tmp_path / "d.wav", .5), AnalysisSettings(fps=24), tmp_path / "cache")


def test_worker_env_drops_pyinstaller_state(tmp_path, monkeypatch):
    seen = {}
    def fake_run(command, **kwargs):
        seen.update(kwargs["env"]); raise RuntimeError("stop")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "x"); monkeypatch.setenv("_MEIPASS2", "y")
    monkeypatch.setattr(analyzer.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="stop"):
        analyzer.analyze_isolated(tmp_path / "e.wav", AnalysisSettings(), tmp_path / "cache")
    assert "_PYI_APPLICATION_HOME_DIR" not in seen and "_MEIPASS2" not in seen and seen["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_queue_runs_set_boundary_only_between_sets(tmp_path):
    manager = QueueManager(state_path=tmp_path / "q.json", load_state=False)
    for name in ("a", "b", "c"):
        manager.add(JobSet.from_dict({"name": name, "output_dir": str(tmp_path), "tracks": [{"audio": f"{name}.wav"}]}))
    manager.sets[1].status = "completed"
    boundaries, rendered = [], []
    result = manager.run(lambda track, job, **_: rendered.append(job["name"]) or {}, between_sets=boundaries.append)
    assert rendered == ["a", "c"] and boundaries == [3] and result.sets_success == 2


def test_set_boundary_waits_for_memory_in_saver_mode(monkeypatch, saver):
    import core.memory_telemetry as telemetry
    readings = iter([500.0, 900.0, 4000.0])
    monkeypatch.setattr(telemetry, "checkpoint", lambda stage, **extra: {"stage": stage, "available_mb": next(readings)})
    saver(True); sleeps, notes = [], []
    data = memory_mode.set_boundary(2, notify=notes.append, sleep=sleeps.append)
    assert data["waited_seconds"] == 10.0 and len(notes) == 2 and "메모리가 부족" in notes[0]["memory_warning"]
    assert sleeps[0] == memory_mode.cooldown_seconds()


def test_set_boundary_never_waits_in_normal_mode_and_honours_cancel(monkeypatch, saver):
    import core.memory_telemetry as telemetry
    monkeypatch.setattr(telemetry, "checkpoint", lambda stage, **extra: {"stage": stage, "available_mb": 100.0})
    saver(False)
    assert memory_mode.set_boundary(2, sleep=lambda _s: None)["waited_seconds"] == 0
    saver(True)
    assert memory_mode.set_boundary(2, cancel=lambda: True, sleep=lambda _s: None)["waited_seconds"] == 0


def test_low_memory_setting_is_persistable(tmp_path):
    from PySide6.QtCore import QSettings
    from core.settings import AppSettings
    settings = AppSettings(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    settings.set("low_memory_mode", False); settings.settings.sync()
    assert str(AppSettings(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)).get("low_memory_mode")).lower() == "false"


def test_main_window_exposes_single_memory_saver_toggle():
    source = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert source.count('QCheckBox("메모리 절약 모드")') == 1
    assert "긴 플레이리스트 작업 시 메모리 사용량을 줄입니다." in source and "self.memory_saver.setChecked(True)" in source


def test_app_dispatches_analysis_worker_before_qt():
    source = Path("app.py").read_text(encoding="utf-8")
    assert source.index("--analysis-worker") < source.index("_configure_logging()\n    args")
