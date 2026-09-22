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
    window=MainWindow(); names=["v074_01_queue.png","v074_02_ready.png","v074_03_progress_10.png","v074_04_progress_50.png","v074_05_complete.png"]
    paths=[]
    for index,name in enumerate(names):
        window.navigate_step(index); path=root/name; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ??? ?... 78%"); window.navigate_step(4); path=root/"v074_03_progress_10.png"; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ???? ???????."); path=root/"v074_05_complete.png"; window.grab().save(str(path)); paths.append(str(path))
    window.queue_panel.refresh(); path=root/"v074_01_queue.png"; window.grab().save(str(path)); paths.append(str(path))
    window.close(); return paths

if __name__ == "__main__": print("\n".join(capture()))
