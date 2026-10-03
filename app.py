import argparse,json,logging,os,sys,tempfile,threading
# numpy and scipy each ship an OpenBLAS pool whose worker threads commit ~32MB
# buffers on Windows (~1.5GB Private on 24 cores). Nothing here needs BLAS
# parallelism, so cap native pools before numpy is first imported.
for _name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ.setdefault(_name,"1")
from logging.handlers import RotatingFileHandler
from pathlib import Path
from core.version import get_version,build_info
from core.runtime_paths import instance_lock_path,logs_dir,running_marker_path,state_dir
def parse_args(argv=None):
    parser=argparse.ArgumentParser(add_help=True);parser.add_argument("--headless",action="store_true");parser.add_argument("--safe-mode",action="store_true");parser.add_argument("--job");parser.add_argument("--audio");parser.add_argument("--preset",default="01_clean_bars");parser.add_argument("--output");parser.add_argument("--format",default="webm",choices=["mp4","webm","mov"]);return parser.parse_args(argv)
def _headless(args):
    from render_job import run_job
    if args.job:return run_job(args.job)
    if not args.audio or not args.output:raise SystemExit("--headless requires --job, or --audio and --output")
    output=Path(args.output);output_dir=output if output.suffix=="" else output.parent
    job={"tracks":[{"audio":args.audio,"preset":args.preset,"format":args.format,**({"output":str(output)} if output.suffix else {})}],"output_dir":str(output_dir),"format":args.format}
    return run_job(job)
def packaged_smoke(window,application):
    from PySide6.QtCore import QTimer
    report={"status":"failed","version":get_version(),"build_info":build_info()}
    try:
        import numpy as np
        from audio.analyzer import analyze_pcm
        from animation.engine import AnimationEngine
        from core.paths import resource_path
        from render.renderer import RendererFactory
        from template_system import load_template
        from ui.roi_widget import ROIImageLabel
        template=load_template(resource_path("templates/01_clean_bars.json"));reference=ROIImageLabel(resource_path("resources/smoke_reference.png"));sr=8000;samples=np.sin(2*np.pi*220*np.arange(sr)/sr).astype(np.float32);features=analyze_pcm(samples,sr,fps=24,bands=16,fft_size=512);state=AnimationEngine(features,template).sample(.25);image=RendererFactory.create("CPU").render_rgba(320,180,state,dict(template,glow=False)); special=load_template(resource_path("templates/23_chill_ribbon.json")); gpu_renderer=RendererFactory.create("AUTO",special); special_image=gpu_renderer.render_rgba(320,180,state,special)
        universal=load_template(resource_path("templates/00_universal_soft_round_led.json"));universal_state=AnimationEngine(features,universal).sample(.25);universal_renderer=RendererFactory.create("AUTO",universal);universal_image=universal_renderer.render_rgba(960,160,universal_state,universal)
        signature_files=("00_v0850_tokyo_two_hearts.json","00_v0850_tokyo_midnight_pulse.json","00_v0850_tokyo_silk_wave.json");signature_results={}
        for signature_file in signature_files:
            signature_template=load_template(resource_path("templates")/signature_file);signature_state=AnimationEngine(features,signature_template).sample(.25);signature_image=RendererFactory.create("AUTO",signature_template).render_rgba(960,160,signature_state,signature_template);signature_results[signature_template["id"]]=int(signature_image[:,:,3].max())
        from visualizers.schema import new_waveform
        from visualizers.user_profiles import UserWaveformStore
        signature_wave=new_waveform("Packaged Tokyo Signature",renderer_family="tokyo_signature",position="LEFT",signature={"variant":"TWO_HEARTS","motion":"DYNAMIC","size":1.0,"vertical_position":"BOTTOM","horizontal_position":"LEFT","presence":"CRISP","auto_adapt":True,"local_adapt":True,"colors":[]});waveform_store=UserWaveformStore(installed_families={"soft_round_led","tokyo_signature"});saved=waveform_store.save(signature_wave,overwrite=True);reloaded=waveform_store.load(saved);exported=waveform_store.export_file(saved,saved.parent/"Packaged_Tokyo_Signature_Export.mwswave");saved.unlink();imported,_=waveform_store.import_file(exported);roundtrip=waveform_store.load(imported);persisted=any(data["name"]=="Packaged Tokyo Signature" for _path,data in waveform_store.list())
        window.template_filter.setCurrentText("Tokyo Chill Signature") if hasattr(window,"template_filter") else None;signature_order=[window.template_list.item(i).text().splitlines()[-1] for i in range(window.template_list.count())];window.signature_controls["Signature"].setCurrentIndex(2);window.reset_signature_defaults();reset_settings=window.template.get("tokyo_signature",{});reset_ok=reset_settings.get("motion")=="DYNAMIC" and reset_settings.get("presence")=="CRISP" and float(reset_settings.get("size",0))==1.0
        imported.unlink(missing_ok=True);exported.unlink(missing_ok=True)
        report={"status":"pass","version":get_version(),"build_info":build_info(),"templates":len(list(Path(resource_path("templates")).glob("*.json"))),"reference_image":not reference.original.isNull(),"audio_frames":len(features["spectrum"]),"preview_shape":list(image.shape),"preview_alpha":int(image[:,:,3].max()),"gpu_renderer":getattr(gpu_renderer,"name","unknown"),"gpu_special_alpha":int(special_image[:,:,3].max()),"universal_renderer":universal_renderer.name,"universal_alpha":int(universal_image[:,:,3].max()),"universal_themes":7,"signature_render":signature_results,"signature_order":signature_order,"signature_recommended_reset":reset_ok,"waveform_saved":reloaded["name"]=="Packaged Tokyo Signature","waveform_restart_persistence":persisted,"waveform_exported":exported.exists() or roundtrip["renderer_family"]=="tokyo_signature","waveform_imported":roundtrip["renderer_family"]=="tokyo_signature" and roundtrip["signature"]["variant"]=="TWO_HEARTS","waveform_storage":str(waveform_store.directory),"ffmpeg":__import__("shutil").which("ffmpeg")}
    except Exception as exc:report={"status":"failed","error":repr(exc)}
    if os.environ.get("MWS_QUEUE_SMOKE")=="1":
        try:
            import wave
            from mws_queue.queue_manager import JobSet,QueueManager
            smoke_root=Path(tempfile.gettempdir())/"mws_queue_smoke_v0852"; smoke_root.mkdir(parents=True,exist_ok=True)
            wav=smoke_root/"smoke.wav"
            with wave.open(str(wav),"wb") as handle:
                handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(8000); handle.writeframes((np.zeros(8000,dtype=np.int16)).tobytes())
            window.queue_manager.state_path=smoke_root/"queue_state.json";window.queue_manager.sets=[];window.queue_manager.save();window.audio_files=[str(wav)];window.audio_list.clear();window.audio_list.addItem(wav.name);window.set_output_dir(str(smoke_root/"wave"));window.navigate_step(3);window.queue_panel.add_button.click();application.processEvents()
            queue_add_ok=len(window.queue_manager.sets)==1 and window.queue_panel.cards.count()==1
            result=window.queue_manager.run(lambda *_:{})
            window._queue_completion(result);application.processEvents()
            ui_completion_ok=not window.queue_manager.sets and window.queue_panel.cards.count()==0 and not window.queue_panel.start_button.isEnabled()
            sequential_ok=ui_completion_ok
            for _ in range(6):
                window.queue_panel.add_button.click();application.processEvents()
                if len(window.queue_manager.sets)!=1:sequential_ok=False;break
                result=window.queue_manager.run(lambda *_:{})
                window._queue_completion(result);application.processEvents()
                sequential_ok=sequential_ok and not window.queue_manager.sets and window.queue_panel.cards.count()==0 and not window.queue_panel.start_button.isEnabled()
            limit_manager=QueueManager(smoke_root/"queue_limit_state.json");limit_manager.sets=[]
            for index in range(5):limit_manager.add(JobSet(f"limit-{index}",[{"audio":str(wav)}],output_dir=str(smoke_root/"wave")))
            try:limit_manager.add(JobSet("limit-6",[{"audio":str(wav)}],output_dir=str(smoke_root/"wave")));limit_enforced=False
            except ValueError:limit_enforced=len(limit_manager.sets)==5
            cancel_path=smoke_root/"queue_cancel_state.json";cancel_manager=QueueManager(cancel_path);cancel_manager.sets=[];cancel_manager.add(JobSet("cancel-smoke",[{"audio":str(wav)},{"audio":str(wav)}],output_dir=str(smoke_root/"wave")))
            cancel_manager.cancel();cancel_manager.cancel();cancel_manager.cancel();repeated_cancel_ok=cancel_manager.cancel_requested
            cancel_result=cancel_manager.run(lambda *_:(cancel_manager.cancel(),{})[1]);cancel_restart=QueueManager(cancel_path);cancel_restart_ok=cancel_result.completed_removed==0 and len(cancel_restart.sets)==1 and cancel_restart.sets[0].status=="cancelled"
            complete_path=smoke_root/"queue_complete_state.json";complete_manager=QueueManager(complete_path);complete_manager.sets=[];complete_manager.add(JobSet("complete-smoke",[{"audio":str(wav)}],output_dir=str(smoke_root/"wave")));complete_manager.run(lambda *_:{});complete_restart_ok=QueueManager(complete_path).sets==[]
            from ui.main_window import TaskWorker
            stop_manager=QueueManager(smoke_root/"queue_stop_state.json");stop_manager.sets=[];stop_manager.add(JobSet("stop-smoke",[{"audio":str(wav)}],output_dir=str(smoke_root/"wave")));stop_manager.running=True;window.worker=TaskWorker("queue",(stop_manager,False));window.worker.runner=stop_manager;window.stop_button.click();application.processEvents();stop_button_ok=stop_manager.cancel_requested and window.isVisible();window.worker=None
            report.update({"queue_add_clicked":queue_add_ok,"queue_count":len(window.queue_manager.sets),"queue_card_visible":queue_add_ok,"queue_step":window.current_step,"queue_start_enabled":window.queue_panel.start_button.isEnabled(),"queue_sequential_jobs":7,"queue_sequential_pass":sequential_ok,"queue_ui_completion_pass":ui_completion_ok,"queue_five_active_limit_pass":limit_enforced,"queue_cancel_interface_pass":hasattr(cancel_manager,"cancel"),"queue_repeated_cancel_pass":repeated_cancel_ok,"queue_stop_button_pass":stop_button_ok,"queue_cancel_restart_pass":cancel_restart_ok,"queue_completion_restart_pass":complete_restart_ok,"queue_completion_message":window.status.text()})
        except Exception as exc: report.update({"queue_add_clicked":False,"queue_error":repr(exc)})
    shot_value=os.environ.get("MWS_SCREENSHOT_DIR")
    if shot_value:
        shot_dir=Path(shot_value)
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
def queue_plan_driver(window,application,plan_path):
    """Test hook (MWS_TEST_QUEUE_PLAN): drive the real UI flow folder -> analyze -> add SETs -> start queue -> idle -> close."""
    from PySide6.QtCore import QTimer
    from template_system import load_template
    from core.memory_telemetry import checkpoint
    plan=json.loads(Path(plan_path).read_text(encoding="utf-8"));report={"status":"running","sets_added":0};report_path=Path(plan.get("report",Path(plan_path).with_suffix(".report.json")))
    extensions={".wav",".mp3",".flac",".m4a",".aac",".ogg",".opus"}
    def files_of(folder,limit):return sorted((str(p) for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in extensions),key=lambda value:Path(value).name.casefold())[:limit]
    def write(**extra):report.update(extra);report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    def when_idle(callback):
        if window.thread is None and not window.queue_manager.running:callback()
        else:QTimer.singleShot(500,lambda:when_idle(callback))
    def add_sets():
        for item in plan["sets"]:
            window.template=load_template(item["template"]);window.sync_controls();window.audio_files=files_of(item["folder"],int(item.get("limit",15)));window.audio_list.clear();window.audio_list.addItems([Path(p).name for p in window.audio_files]);Path(item["output"]).mkdir(parents=True,exist_ok=True);window.set_output_dir(item["output"])
            if window.add_to_queue():report["sets_added"]+=1
        write();checkpoint("test_queue_start",sets=report["sets_added"]);window.start_queue();QTimer.singleShot(1000,lambda:when_idle(finished))
    def finished():
        write(status="queue_done",queue_remaining=len(window.queue_manager.sets),statuses=[item.status for item in window.queue_manager.sets]);checkpoint("test_queue_idle_begin")
        QTimer.singleShot(int(plan.get("idle_ms",30000)),lambda:(checkpoint("test_queue_idle_end"),write(status="closing"),window.close()))
    def begin():
        first=plan["sets"][0];window.template=load_template(first["template"]);window.sync_controls();window.audio_files=files_of(first["folder"],int(first.get("limit",15)));window.audio_list.addItems([Path(p).name for p in window.audio_files]);Path(first["output"]).mkdir(parents=True,exist_ok=True);window.set_output_dir(first["output"]);window.analyze_audio()
        QTimer.singleShot(500,lambda:when_idle(add_sets))
    write(status="waiting");QTimer.singleShot(int(plan.get("start_delay_ms",0)),begin)
def _configure_logging():
    root=logs_dir();root.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(root/"music_wave_studio.log",maxBytes=5*1024*1024,backupCount=3,encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"));logging.basicConfig(level=logging.INFO,handlers=[handler],force=True)
    logging.info("Music Wave Studio version=%s os=%s executable=%s",get_version(),sys.platform,sys.executable)
    def log_unhandled(kind,value,traceback):logging.critical("unhandled exception",exc_info=(kind,value,traceback));sys.__excepthook__(kind,value,traceback)
    sys.excepthook=log_unhandled
    def log_thread(args):logging.critical("thread exception name=%s",args.thread.name if args.thread else "unknown",exc_info=(args.exc_type,args.exc_value,args.exc_traceback))
    threading.excepthook=log_thread

def _install_qt_logging():
    from PySide6.QtCore import qInstallMessageHandler
    def handler(mode,context,message):
        name=getattr(mode,"name",str(mode));level=logging.CRITICAL if "Fatal" in name else logging.WARNING if "Warning" in name or "Critical" in name else logging.DEBUG
        logging.log(level,"QT type=%s file=%s line=%s message=%s",name,getattr(context,"file",None),getattr(context,"line",None),message)
    qInstallMessageHandler(handler)

def main(argv=None):
    _configure_logging()
    args=parse_args(argv)
    if args.headless:
        result=_headless(args);print(json.dumps(result,ensure_ascii=False));return 0 if not result["failed"] else 2
    from PySide6.QtCore import QLockFile,QTimer
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtGui import QFont, QFontDatabase
    app=QApplication(sys.argv[:1]); app.setApplicationName(f"Music Wave Studio v{get_version()}"); app.setOrganizationName("MusicWaveStudio")
    _install_qt_logging();state_dir().mkdir(parents=True,exist_ok=True)
    instance_lock=QLockFile(str(instance_lock_path()));instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(100):
        logging.info("INSTANCE second launch rejected")
        if os.environ.get("MWS_TEST_NONINTERACTIVE")!="1":QMessageBox.information(None,"Music Wave Studio","Music Wave Studio가 이미 실행 중입니다.")
        return 0
    marker=running_marker_path();previous_crash=marker.exists()
    safe_mode=args.safe_mode
    if previous_crash and not safe_mode:
        safe_mode=QMessageBox.question(None,"Music Wave Studio 복구","이전 실행이 비정상 종료되었습니다.\n안전 모드로 시작하시겠습니까?",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes
    try:marker.write_text(f"pid={os.getpid()}\nversion={get_version()}\n",encoding="utf-8")
    except OSError:logging.exception("CRASH marker create failed path=%s",marker)
    def normal_shutdown():
        try:marker.unlink(missing_ok=True)
        except OSError:logging.exception("CRASH marker cleanup failed path=%s",marker)
        instance_lock.unlock()
    app.aboutToQuit.connect(normal_shutdown)
    families=set(QFontDatabase.families()); chosen=next((name for name in ("Malgun Gothic","Noto Sans CJK KR","Segoe UI") if name in families), None); chosen and app.setFont(QFont(chosen,10))
    try:
        from ui.main_window import MainWindow
        window=MainWindow(safe_mode=safe_mode);window.show();logging.info("STARTUP phase=show_window ok safe_mode=%s",safe_mode)
    except Exception:
        logging.exception("STARTUP MainWindow construction failed")
        QMessageBox.critical(None,"Music Wave Studio","프로그램 시작 중 오류가 발생했습니다.\n로그 위치: "+str(logs_dir()/"music_wave_studio.log"))
        normal_shutdown();return 1


    if os.environ.get("MWS_SMOKE_TEST")=="1":QTimer.singleShot(0,lambda:packaged_smoke(window,app))
    from core.memory_telemetry import checkpoint as memory_checkpoint
    QTimer.singleShot(1500,lambda:memory_checkpoint("app_ready",safe_mode=safe_mode))
    if os.environ.get("MWS_TEST_QUEUE_PLAN"):QTimer.singleShot(2000,lambda:queue_plan_driver(window,app,os.environ["MWS_TEST_QUEUE_PLAN"]))
    auto_close=os.environ.get("MWS_AUTO_CLOSE_MS")
    if auto_close:QTimer.singleShot(max(1,int(auto_close)),window.close)
    return app.exec()
if __name__=="__main__":raise SystemExit(main())

