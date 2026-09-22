import json,os,sys,tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def packaged_smoke(window,application):
    report={"status":"failed"}
    try:
        import numpy as np
        from audio.analyzer import analyze_pcm
        from animation.engine import AnimationEngine
        from core.paths import resource_path
        from render.renderer import RendererFactory
        from template_system import load_template
        from ui.roi_widget import ROIImageLabel
        template=load_template(resource_path("templates/01_clean_bars.json"));reference=ROIImageLabel(resource_path("resources/smoke_reference.png"));sr=8000;samples=np.sin(2*np.pi*220*np.arange(sr)/sr).astype(np.float32);features=analyze_pcm(samples,sr,fps=24,bands=16,fft_size=512);state=AnimationEngine(features,template).sample(.25);image=RendererFactory.create("CPU").render_rgba(320,180,state,dict(template,glow=False));report={"status":"pass","templates":window.template_list.count(),"reference_image":not reference.original.isNull(),"audio_frames":len(features["spectrum"]),"preview_shape":list(image.shape),"preview_alpha":int(image[:,:,3].max()),"ffmpeg":__import__("shutil").which("ffmpeg")}
    except Exception as exc:report={"status":"failed","error":repr(exc)}
    target=Path(os.environ.get("MWS_SMOKE_REPORT",Path(tempfile.gettempdir())/"music_wave_smoke.json"));target.write_text(json.dumps(report,indent=2),encoding="utf-8");QTimer.singleShot(50,application.quit)
def main():
    app=QApplication(sys.argv);app.setApplicationName("Music Wave Studio");window=MainWindow();window.show()
    if os.environ.get("MWS_SMOKE_TEST")=="1":QTimer.singleShot(0,lambda:packaged_smoke(window,app))
    return app.exec()
if __name__=="__main__":raise SystemExit(main())
