from __future__ import annotations
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def capture(output_dir: str = "validation_results") -> list[str]:
    root=Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    app=QApplication.instance() or QApplication([])
    window=MainWindow(); names=["v076_01_reference_idle.png","v076_02_reference_clicked.png","v076_03_reference_progress.png","v076_04_reference_complete.png","v076_05_roi_fallback.png"]
    paths=[]
    for index,name in enumerate(names):
        window.navigate_step(index); path=root/name; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ??? ?... 78%"); window.navigate_step(4); path=root/"v076_03_reference_progress.png"; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ???? ???????."); path=root/"v076_05_roi_fallback.png"; window.grab().save(str(path)); paths.append(str(path))
    window.queue_panel.refresh(); path=root/"v076_01_reference_idle.png"; window.grab().save(str(path)); paths.append(str(path))
    window.close(); return paths

if __name__ == "__main__": print("\n".join(capture()))
