import wave, numpy as np, pytest
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

@pytest.fixture
def workflow(tmp_path):
    app=QApplication.instance() or QApplication([]); p=tmp_path/'song.wav'; h=wave.open(str(p),'wb'); h.setnchannels(1); h.setsampwidth(2); h.setframerate(8000); h.writeframes((np.zeros(8000,dtype=np.int16)).tobytes()); h.close(); w=MainWindow(); w.app_settings.set('first_run_done',True); w.queue_manager.state_path=tmp_path/'queue.json'; w.audio_files=[str(p)]; w.audio_list.addItem(p.name); w.set_output_dir(str(tmp_path/'wave')); yield w; w.close()

def test_queue_add_without_preview_and_step4(workflow):
    workflow.navigate_step(2); assert workflow.add_to_queue() is True; assert len(workflow.queue_manager.sets)==1; assert workflow.current_step==3

def test_start_cta_visible_and_enabled(workflow):
    workflow.show(); workflow.add_to_queue(); workflow.navigate_step(4); assert workflow.primary_action.isVisible() and workflow.primary_action.isEnabled(); assert '시작' in workflow.primary_action.text()

def test_pause_and_resume_queue_state(workflow):
    workflow.add_to_queue(); workflow.queue_manager.request_pause(); assert workflow.queue_manager.pause_requested; workflow.queue_manager.resume(); assert not workflow.queue_manager.pause_requested

def test_empty_queue_has_clear_start_state(qapp=None):
    app=QApplication.instance() or QApplication([]); w=MainWindow(); w.queue_manager.clear(); w.navigate_step(4); assert not w.primary_action.isEnabled(); w.close()

