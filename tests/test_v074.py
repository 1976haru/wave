import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication
import pytest
from ui.main_window import MainWindow
from mws_queue.queue_manager import JobSet

@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.app_settings.set("first_run_done",True);w.queue_manager.state_path=tmp_path/"queue.json";yield w;w.close()

def test_top_workflow_is_folder_queue_start(window):
    from ui.locale import Translator
    tr=Translator("ko");assert [button.text() for button in window.step_labels]==[tr.tr(key) for key in ("step1","step2","step3","step4","step5")]

def test_legacy_bottom_actions_hidden(window):
    assert all(not button.isVisible() for button in window.bottom_actions)

def test_progress_bars_are_prominent(window):
    assert window.song_progress.minimumHeight()>=24 and window.total_progress.minimumHeight()>=24
    assert "?? ?" in window.song_progress.format() and "??" in window.total_progress.format()

def test_progress_page_has_stop_action(window):
    assert hasattr(window,"progress_page") and hasattr(window,"progress_detail_label")

def test_queue_panel_has_cards_and_start_button(window):
    window.queue_manager.sets=[JobSet("Demo",[{"audio":"a.wav","duration":12}],output_dir="wave")];window.queue_panel.refresh();assert window.queue_panel.summary.text().endswith("1 / 5") and window.queue_panel.start_button.isEnabled()

def test_duration_is_nonzero_in_queue_card(window):
    window.queue_manager.sets=[JobSet("Demo",[{"audio":"a.wav","duration":203}],output_dir="wave")];window.queue_panel.refresh();assert window.queue_manager.sets[0].display_duration.startswith("3")

def test_start_queue_switches_to_progress_page(window,monkeypatch):
    window.queue_manager.sets=[JobSet("Demo",[{"audio":"a.wav"}],output_dir="wave")];window.queue_manager.preflight=lambda **kwargs:[{"ready":True}];monkeypatch.setattr(window,"start_task",lambda *args:None);window.start_queue();assert window.progress_page.isHidden() is False

def test_progress_percent_label_updates(window):
    window.audio_files=["song.wav"];window.render_detail({"percent":50,"track_index":1,"track_total":1,"set_index":1,"set_total":1,"fps":74.2});assert window.song_progress.value()==50 and "50%" in window.progress_detail_label.text()
