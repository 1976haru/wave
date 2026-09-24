from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def test_default_webm_uses_overlay_canvas():
 app=QApplication.instance() or QApplication([]); w=MainWindow(); w.queue_manager.sets=[]; snap=w.build_current_job_snapshot(); assert snap['options'].canvas_mode=='overlay'; assert (snap['options'].width,snap['options'].height)==(960,240); w.close()