from pathlib import Path
import wave,numpy as np
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from core.version import get_version

def test_version_single_source():
    assert get_version()==Path('VERSION.txt').read_text(encoding='utf-8-sig').strip()

def test_queue_panel_add_button_is_connected(tmp_path):
    app=QApplication.instance() or QApplication([])
    p=tmp_path/'song.wav'
    with wave.open(str(p),'wb') as h:
        h.setnchannels(1);h.setsampwidth(2);h.setframerate(8000);h.writeframes(np.zeros(8000,dtype=np.int16).tobytes())
    w=MainWindow();w.app_settings.set('first_run_done',True);w.queue_manager.state_path=tmp_path/'queue.json';w.queue_manager.sets=[];w.audio_files=[str(p)];w.audio_list.addItem(p.name);w.set_output_dir(str(tmp_path/'wave'));w.navigate_step(3)
    w.queue_panel.add_button.click(); app.processEvents()
    assert len(w.queue_manager.sets)==1 and w.current_step==3 and w.queue_panel.summary.text().endswith('1 / 5')
    w.close()

