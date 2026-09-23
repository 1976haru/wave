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
    window=MainWindow(); names=["v075_01_folder_korean.png","v075_02_reference_loaded.png","v075_03_reference_running.png","v075_04_reference_result.png","v075_05_reference_roi_fallback.png"]
    paths=[]
    for index,name in enumerate(names):
        window.navigate_step(index); path=root/name; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ??? ?... 78%"); window.navigate_step(4); path=root/"v075_03_reference_running.png"; window.grab().save(str(path)); paths.append(str(path))
    window.status.setText("?? ???? ???????."); path=root/"v075_05_reference_roi_fallback.png"; window.grab().save(str(path)); paths.append(str(path))
    window.queue_panel.refresh(); path=root/"v075_01_folder_korean.png"; window.grab().save(str(path)); paths.append(str(path))
    window.close(); return paths

if __name__ == "__main__": print("\n".join(capture()))
