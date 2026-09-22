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
    window=MainWindow(); names=["v073_01_folder.png","v073_02_style.png","v073_03_preview.png","v073_04_queue.png","v073_05_ready.png"]
    paths=[]
    for index,name in enumerate(names):
        window.navigate_step(index); path=root/name; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ??? ?... 78%"); window.navigate_step(4); path=root/"v073_06_progress.png"; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ???? ???????."); path=root/"v073_07_complete.png"; window.grab().save(str(path)); paths.append(str(path))
    window.queue_panel.refresh(); path=root/"v073_08_queue.png"; window.grab().save(str(path)); paths.append(str(path))
    window.close(); return paths

if __name__ == "__main__": print("\n".join(capture()))
