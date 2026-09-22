import os
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication,QFileDialog,QPushButton
import pytest
from ui.main_window import MainWindow
@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([])
    w=MainWindow();w.queue_manager.state_path=tmp_path/"queue.json";w.queue_manager.sets=[];w.app_settings.set("first_run_done",True);w.app_settings.set("last_output_folder","");w.current_output_dir="";yield w;w.close()
def test_render_now_uses_automatic_wave_folder(window,monkeypatch,tmp_path):
    audio=tmp_path/"song.wav";audio.write_bytes(b"x");window.audio_files=[str(audio)];calls=[];monkeypatch.setattr(QFileDialog,"getExistingDirectory",staticmethod(lambda *args:(calls.append(1) or str(tmp_path))));started=[];monkeypatch.setattr(window,"start_task",lambda kind,payload:started.append((kind,payload)))
    assert window.render() is True
    assert len(calls)==0 and window.current_output_dir==str((tmp_path/"wave").resolve()) and started and started[0][0]=="render"

def test_render_now_reuses_saved_folder(window,monkeypatch,tmp_path):
    audio=tmp_path/"song.wav";audio.write_bytes(b"x");window.audio_files=[str(audio)];window.set_output_dir(tmp_path);calls=[];monkeypatch.setattr(QFileDialog,"getExistingDirectory",staticmethod(lambda *args:(calls.append(1) or str(tmp_path))));monkeypatch.setattr(window,"start_task",lambda *args:None)
    assert window.render() is True and len(calls)==0
def test_render_without_audio_does_not_start(window,monkeypatch):
    calls=[];monkeypatch.setattr(QFileDialog,"getExistingDirectory",staticmethod(lambda *args:(calls.append(1) or "")));started=[];monkeypatch.setattr(window,"start_task",lambda *args:started.append(args))
    assert window.render() is False and len(calls)==0 and not started

def test_job_snapshot_contains_frozen_template_and_output(window,tmp_path):
    window.audio_files=["song.wav"];window.template["name"]="Tokyo Night";window.set_output_dir(tmp_path);snapshot=window.build_current_job_snapshot();window.template["name"]="Changed"
    assert snapshot["output_dir"]==str(tmp_path.resolve()) and snapshot["template"]["name"]=="Tokyo Night" and snapshot["audio_files"]==["song.wav"]
def test_step_buttons_are_clickable(window):
    assert all(isinstance(button,QPushButton) and button.isCheckable() for button in window.step_labels)
    window.step_labels[3].click();assert window.current_step==3 and window.tabs.currentIndex()==4
    window.step_labels[0].click();assert window.current_step==0
def test_step_navigation_previous_and_next(window):
    for index in range(5):window.navigate_step(index);assert window.current_step==index
def test_output_folder_is_saved_to_settings(window,tmp_path):
    window.set_output_dir(tmp_path);assert Path(window.app_settings.get("last_output_folder")).resolve()==tmp_path.resolve()
def test_automatic_analysis_after_audio_selection(window,monkeypatch,tmp_path):
    audio=tmp_path/"song.wav";audio.write_bytes(b"x");started=[]
    monkeypatch.setattr(QFileDialog,"getOpenFileNames",staticmethod(lambda *args:([str(audio)],"")))
    monkeypatch.setattr(window,"start_task",lambda kind,payload:started.append((kind,payload)))
    window.add_audio()
    assert started and started[0][0]=="analysis" and window.current_step==1
def test_style_selection_navigates_to_preview(window):
    item=window.template_list.item(0);window.apply_gallery(item);assert window.current_step==2
def test_export_default_is_transparent_webm(window):
    assert window.export_format.currentText()=="webm"
def test_advanced_controls_are_hidden_by_default(window):
    assert [window.tabs.isTabVisible(i) for i in range(window.tabs.count())][1:4]==[False,False,False]
def test_advanced_controls_can_be_revealed(window):
    window.toggle_advanced(True);assert all(window.tabs.isTabVisible(i) for i in range(1,4))
def test_queue_add_uses_current_output_without_dialog(window,monkeypatch,tmp_path):
    audio=tmp_path/"song.wav";audio.write_bytes(b"x");window.audio_files=[str(audio)];window.set_output_dir(tmp_path);calls=[];monkeypatch.setattr(QFileDialog,"getExistingDirectory",staticmethod(lambda *args:(calls.append(1) or str(tmp_path))));assert window.add_to_queue() is True and not calls and len(window.queue_manager.sets)>=1
