import json
import os
from pathlib import Path

import pytest

from app import parse_args
from core.runtime_paths import app_data_root, cache_dir, queue_state_path, running_marker_path
from mws_queue.queue_manager import JobSet, QueueManager


def test_runtime_paths_are_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert app_data_root() == tmp_path / "MusicWaveStudio"
    assert queue_state_path() == tmp_path / "MusicWaveStudio" / "state" / "queue_state.json"
    assert cache_dir() == tmp_path / "MusicWaveStudio" / "cache"


def test_default_queue_never_uses_working_directory(monkeypatch, tmp_path):
    local = tmp_path / "local"
    work = tmp_path / "work"; work.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local));monkeypatch.chdir(work)
    manager = QueueManager(migrate=False)
    assert manager.state_path == local / "MusicWaveStudio" / "state" / "queue_state.json"


def test_legacy_migration_normalizes_and_keeps_backup(monkeypatch, tmp_path):
    local = tmp_path / "local";legacy = tmp_path / "legacy" / "queue_state.json";legacy.parent.mkdir()
    legacy.write_text(json.dumps({"sets":[
        {"name":"done","tracks":[],"status":"completed"},
        {"name":"active","tracks":[{"audio":"a.wav"}],"status":"running"},
        {"name":"failed","tracks":[],"status":"failed"},
        {"name":"cancelled","tracks":[],"status":"cancelled"},
    ]}), encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(QueueManager,"_legacy_candidates",lambda self:[legacy])
    manager=QueueManager()
    assert [item.status for item in manager.sets]==["pending","failed","cancelled"]
    assert legacy.exists()
    assert list(legacy.parent.glob("queue_state_migrated_backup_*.json"))


@pytest.mark.parametrize("content",["", "{", "\udcff", "[]", '{"sets":[null]}', '{"sets":[{"name":"x","tracks":null}]}'])
def test_corrupt_queue_is_quarantined(monkeypatch,tmp_path,content):
    state=tmp_path/"queue_state.json"
    if content=="\udcff":state.write_bytes(b"\xff\xfe\x00")
    else:state.write_text(content,encoding="utf-8")
    manager=QueueManager(state,migrate=False)
    assert manager.sets==[] and manager.load_warning
    assert list(tmp_path.glob("queue_state.corrupt.*.json"))


def test_atomic_save_leaves_no_temp(tmp_path):
    state=tmp_path/"queue_state.json";manager=QueueManager(state,migrate=False)
    manager.add(JobSet("one",[{"audio":"a.wav"}]))
    assert json.loads(state.read_text(encoding="utf-8"))["sets"][0]["name"]=="one"
    assert not state.with_name(state.name+".tmp").exists()


def test_completed_pruned_and_running_recovers(tmp_path):
    state=tmp_path/"queue_state.json";state.write_text(json.dumps({"sets":[{"name":"a","tracks":[],"status":"completed"},{"name":"b","tracks":[],"status":"running"}]}),encoding="utf-8")
    manager=QueueManager(state,migrate=False)
    assert len(manager.sets)==1 and manager.sets[0].status=="pending"


def test_failed_and_cancelled_are_retryable(tmp_path):
    state=tmp_path/"queue_state.json";manager=QueueManager(state,migrate=False)
    manager.sets=[JobSet("failed",[{"audio":"a"}],status="failed"),JobSet("cancelled",[{"audio":"b"}],status="cancelled")]
    result=manager.run(lambda *_:{})
    assert result.sets_success==2 and manager.sets==[]


def test_safe_mode_cli():
    assert parse_args(["--safe-mode"]).safe_mode is True


def test_crash_marker_is_in_state_dir(monkeypatch,tmp_path):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path))
    assert running_marker_path().parent==tmp_path/"MusicWaveStudio"/"state"


def test_startup_resume_does_not_call_start_queue():
    source=Path("ui/main_window.py").read_text(encoding="utf-8")
    body=source.split("def _first_run_and_resume",1)[1].split("def _queue_completion",1)[0]
    assert "self.start_queue()" not in body


def test_cancel_is_idempotent(tmp_path):
    manager=QueueManager(tmp_path/"queue_state.json",migrate=False)
    for _ in range(20):manager.cancel()
    assert manager.cancel_requested


def test_single_instance_lock(tmp_path):
    from PySide6.QtCore import QLockFile
    first=QLockFile(str(tmp_path/"instance.lock"));second=QLockFile(str(tmp_path/"instance.lock"));first.setStaleLockTime(0);second.setStaleLockTime(0)
    assert first.tryLock(0);assert not second.tryLock(0);first.unlock();assert second.tryLock(0);second.unlock()


def test_invalid_settings_fall_back_without_startup_crash(monkeypatch,tmp_path):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path))
    monkeypatch.setenv("MWS_AUTO_CLOSE_MS","1")
    from PySide6.QtWidgets import QApplication
    from core.settings import AppSettings
    settings=AppSettings();settings.set("renderer_mode","BROKEN");settings.set("quality",None);settings.set("resolution","999xBAD");settings.set("fps","zero");settings.set("ffmpeg_path",str(tmp_path/"missing.exe"))
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([]);window=MainWindow()
    assert window.renderer_choice.currentText()=="AUTO"
    assert window.quality.currentText()=="BALANCED"
    assert window.resolution.currentText()=="1920x1080"
    assert window.export_fps.currentText()=="30"
    assert window.ffmpeg_path.text()==""
    window.close();app.processEvents()


def test_close_event_isolates_settings_failure(monkeypatch,tmp_path):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path));monkeypatch.setenv("MWS_AUTO_CLOSE_MS","1")
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([]);window=MainWindow(safe_mode=True)
    def fail(_window):raise OSError("simulated settings failure")
    window.app_settings.save_window=fail
    window.close();app.processEvents()
    assert window.shutting_down
