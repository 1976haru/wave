import os
from pathlib import Path
from core.ffmpeg_progress import FFmpegProgressParser
from pipeline.exporter import build_ffmpeg_command, ExportOptions
from ui.main_window import MainWindow
from PySide6.QtWidgets import QApplication,QFileDialog
import pytest

@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([]); w=MainWindow(); w.app_settings.set("first_run_done",True); w.app_settings.set("last_output_folder",""); w.current_output_dir=""; w.queue_manager.state_path=tmp_path/"queue.json"; yield w; w.close()

def test_ffmpeg_progress_parser_percent():
    p=FFmpegProgressParser(100); assert p.feed("out_time_ms=10000000")["percent"]==10.0; assert p.feed("out_time_ms=50000000")["percent"]==50.0; assert p.feed("progress=end")["done"]

def test_ffmpeg_progress_parser_frame_fps():
    p=FFmpegProgressParser(10); p.feed("frame=12"); p.feed("fps=30.5"); e=p.feed("out_time_ms=1000000"); assert e["frame"]==12 and e["fps"]==30.5

def test_ffmpeg_command_requests_progress():
    cmd=build_ffmpeg_command("ffmpeg", "x.mp4", ExportOptions(format="mp4"), "a.wav"); assert "-progress" in cmd and "pipe:2" in cmd and "-nostats" in cmd

def test_folder_discovery_and_wave_output(window,monkeypatch,tmp_path):
    monkeypatch.setattr(window,"start_task",lambda *args:None)
    (tmp_path/"02.mp3").write_bytes(b"x");(tmp_path/"01.wav").write_bytes(b"x");(tmp_path/"note.txt").write_text("x")
    monkeypatch.setattr(QFileDialog,"getExistingDirectory",staticmethod(lambda *a:str(tmp_path)))
    assert window.add_folder() and [Path(x).name for x in window.audio_files]==["01.wav","02.mp3"]; assert Path(window.current_output_dir)==tmp_path/"wave"

def test_folder_discovery_rejects_empty(window,monkeypatch,tmp_path):
    monkeypatch.setattr(QFileDialog,"getExistingDirectory",staticmethod(lambda *a:str(tmp_path))); assert not window.add_folder()

def test_automatic_output_reuses_existing_wave(window,tmp_path):
    audio=tmp_path/"a.wav";audio.write_bytes(b"x");window.audio_files=[str(audio)]; assert Path(window.ensure_output_dir())==tmp_path/"wave"; assert Path(window.ensure_output_dir()).is_dir()

def test_progress_detail_updates_ui(window):
    window.audio_files=["song.wav"]; window.render_detail({"percent":72,"track_index":1,"track_total":15,"set_index":2,"set_total":5,"fps":72.3}); assert window.song_progress.value()==72 and "?? 2 / 5" in window.status.text()

def test_hidden_process_kwargs_is_windows_safe():
    from pipeline.exporter import _hidden_process_kwargs
    values=_hidden_process_kwargs(); assert values["stdin"] is not None and "stderr" in values

def test_wave_folder_does_not_delete_existing(window,tmp_path):
    wave=tmp_path/"wave";wave.mkdir();marker=wave/"keep.txt";marker.write_text("keep");audio=tmp_path/"a.wav";audio.write_bytes(b"x");window.audio_files=[str(audio)];window.ensure_output_dir();assert marker.exists()

def test_skip_completed_default(window):
    assert window.skip_completed.isChecked()
