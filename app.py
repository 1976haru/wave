import argparse,json,os,sys,tempfile
from pathlib import Path
def parse_args(argv=None):
    parser=argparse.ArgumentParser(add_help=True);parser.add_argument("--headless",action="store_true");parser.add_argument("--job");parser.add_argument("--audio");parser.add_argument("--preset",default="01_clean_bars");parser.add_argument("--output");parser.add_argument("--format",default="webm",choices=["mp4","webm","mov"]);return parser.parse_args(argv)
def _headless(args):
    from render_job import run_job
    if args.job:return run_job(args.job)
    if not args.audio or not args.output:raise SystemExit("--headless requires --job, or --audio and --output")
    output=Path(args.output);output_dir=output if output.suffix=="" else output.parent
    job={"tracks":[{"audio":args.audio,"preset":args.preset,"format":args.format,**({"output":str(output)} if output.suffix else {})}],"output_dir":str(output_dir),"format":args.format}
    return run_job(job)
def packaged_smoke(window,application):
    from PySide6.QtCore import QTimer
    report={"status":"failed"}
    try:
        import numpy as np
        from audio.analyzer import analyze_pcm
        from animation.engine import AnimationEngine
        from core.paths import resource_path
        from render.renderer import RendererFactory
        from template_system import load_template
        from ui.roi_widget import ROIImageLabel
        template=load_template(resource_path("templates/01_clean_bars.json"));reference=ROIImageLabel(resource_path("resources/smoke_reference.png"));sr=8000;samples=np.sin(2*np.pi*220*np.arange(sr)/sr).astype(np.float32);features=analyze_pcm(samples,sr,fps=24,bands=16,fft_size=512);state=AnimationEngine(features,template).sample(.25);image=RendererFactory.create("CPU").render_rgba(320,180,state,dict(template,glow=False));window.template_filter.setCurrentIndex(1) if hasattr(window,"template_filter") else None; report={"status":"pass","templates":len(list(Path(resource_path("templates")).glob("*.json"))),"reference_image":not reference.original.isNull(),"audio_frames":len(features["spectrum"]),"preview_shape":list(image.shape),"preview_alpha":int(image[:,:,3].max()),"ffmpeg":__import__("shutil").which("ffmpeg")}
    except Exception as exc:report={"status":"failed","error":repr(exc)}
    shot_dir=Path(os.environ.get("MWS_SCREENSHOT_DIR",""));
    if shot_dir:
        shot_dir.mkdir(parents=True,exist_ok=True);window.grab().save(str(shot_dir/"gui_simple_korean.png"));window.left_tabs.setCurrentWidget(window.queue_panel);window.grab().save(str(shot_dir/"gui_queue_korean.png"))
    target=Path(os.environ.get("MWS_SMOKE_REPORT",Path(tempfile.gettempdir())/"music_wave_smoke.json"))
    if os.environ.get("MWS_REFERENCE_SMOKE")=="1":
        try:
            import cv2,numpy as np
            ref=Path(tempfile.gettempdir())/"mws_reference_smoke.jpg";cv2.imwrite(str(ref),np.zeros((240,320,3),np.uint8));window.reference_images=[str(ref)];window.analyze_reference_images()
            def poll_reference():
                if window.reference_worker is None:
                    report.update({"reference_button":window.reference_analyze_button.text(),"reference_status":window.reference_status.text(),"reference_completed":window.reference_analyze_button.isEnabled()});target.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8");application.quit()
                else:QTimer.singleShot(50,poll_reference)
            QTimer.singleShot(50,poll_reference);return
        except Exception as exc:report.update({"reference_status":"failed","reference_error":repr(exc)})
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8");QTimer.singleShot(50,application.quit)
def main(argv=None):
    args=parse_args(argv)
    if args.headless:
        result=_headless(args);print(json.dumps(result,ensure_ascii=False));return 0 if not result["failed"] else 2
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    app=QApplication(sys.argv[:1]);app.setApplicationName("Music Wave Studio");app.setOrganizationName("MusicWaveStudio");window=MainWindow();window.show()
    if os.environ.get("MWS_SMOKE_TEST")=="1":QTimer.singleShot(0,lambda:packaged_smoke(window,app))
    return app.exec()
if __name__=="__main__":raise SystemExit(main())

