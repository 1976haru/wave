from __future__ import annotations
import copy,time,datetime,os,subprocess,wave
from pathlib import Path
import numpy as np
from PySide6.QtCore import QObject,QMetaObject,QThread,QTimer,QUrl,QSize,Signal,Slot,Qt
from PySide6.QtGui import QColor,QIcon,QImage,QPixmap,QFont,QFontDatabase
from PySide6.QtMultimedia import QAudioOutput,QMediaPlayer
from PySide6.QtWidgets import (QApplication,QCheckBox,QColorDialog,QComboBox,QFileDialog,QFormLayout,QGroupBox,QHBoxLayout,QInputDialog,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMainWindow,QMessageBox,QProgressBar,QPushButton,QScrollArea,QSlider,QSpinBox,QDoubleSpinBox,QTabWidget,QVBoxLayout,QWidget)
from audio.analyzer import AnalysisSettings,analyze_file
from core.paths import resource_path
from core.version import get_version
from core.settings import AppSettings
from core.storage import disk_warning
from ui.locale import Translator,TRANSLATIONS
from ui.queue_panel import QueuePanel
from ui.simple_controls import SimpleControls
from mws_queue.queue_manager import JobSet,QueueManager
from mws_queue.sleep_prevention import SleepPrevention
from ui.playlist_panel import PlaylistPanel
from animation.engine import AnimationEngine
from pipeline.batch import BatchRunner
from pipeline.exporter import ExportOptions,output_extension
from render_job import run_job,resolve_template
from pipeline.exporter import render_audio
from pipeline.segment_resume import ensure_manifest,SEGMENT_SECONDS
from pipeline.segment_renderer import render_segmented_track
from pipeline.set_renderer import render_set
from preview.engine import PreviewEngine,format_time
from preview.scheduler import FrameScheduler
from preview.worker import LatestFrameMailbox,PreviewRenderWorker
from reference.analyzer import analyze_images,analyze_video
from render.renderer import CPURenderer,RendererFactory
from template_system import list_templates,load_template,save_template
from template_system.thumbnails import get_thumbnail
from ui.roi_widget import ROIDialog
from tools.system_check import check_system,format_report
from tools.validate_audio import validate as validate_audio_folder

class ReferenceAnalysisWorker(QObject):
    started=Signal();stage_changed=Signal(str,int,int);result_ready=Signal(object);warning=Signal(str);failed=Signal(str);cancelled=Signal();finished=Signal()
    def __init__(self,paths,roi=None):super().__init__();self.paths=paths;self.roi=roi;self.cancel_requested=False
    @Slot()
    def run(self):
        self.started.emit()
        try:
            if self.cancel_requested:self.cancelled.emit();return
            self.stage_changed.emit("\uc774\ubbf8\uc9c0 \ubd88\ub7ec\uc624\ub294 \uc911",1,4)
            self.stage_changed.emit("\ud30c\ud615 \uc601\uc5ed \ucc3e\ub294 \uc911",2,4)
            self.stage_changed.emit("\uc0c9\uc0c1\uacfc \ud615\ud0dc \ubd84\uc11d \uc911",3,4)
            result=analyze_images(self.paths,self.roi)
            if self.cancel_requested:self.cancelled.emit();return
            self.stage_changed.emit("\ud30c\ud615 \uc2a4\ud0c0\uc77c \ub9cc\ub4dc\ub294 \uc911",4,4);self.result_ready.emit(result)
        except Exception as exc:self.failed.emit(str(exc))
        finally:self.finished.emit()
    @Slot()
    def cancel(self):self.cancel_requested=True

class TaskWorker(QObject):
    done=Signal(object);failed=Signal(str);status=Signal(str);progress=Signal(int,int);detail=Signal(object)
    def __init__(self,kind,payload):super().__init__();self.kind=kind;self.payload=payload;self.runner=None
    @Slot()
    def run(self):
        try:
            if self.kind=="analysis":
                started=time.perf_counter(); features,hit=analyze_file(self.payload[0],self.payload[1] if isinstance(self.payload[1],AnalysisSettings) else AnalysisSettings(fps=24,bands=self.payload[1]),logger=self.status.emit); result=(features,hit,time.perf_counter()-started)
            elif self.kind=="render":
                files,out,template,options,skip_completed=self.payload;self.runner=BatchRunner();result=self.runner.run(files,out,template,options,skip_completed=skip_completed,progress=lambda a,b,e:(self.progress.emit(a,b),self.status.emit(f"ETA {e:.0f}s")),progress_detail=self.detail.emit)
            elif self.kind=="images":result=analyze_images(*self.payload)
            elif self.kind=="video":result=analyze_video(*self.payload)
            elif self.kind=="validation":result=validate_audio_folder(*self.payload)
            elif self.kind=="playlist":result=run_job(self.payload)
            elif self.kind=="queue":
                manager,sleep_enabled=self.payload
                def render_track(track,job,progress_detail=None):
                    source=Path(track.get("audio",track.get("source_path",""))); fmt=track.get("format",job.get("export",{}).get("format","webm")); export={**job.get("export",{}),**track.get("export",{})}; resolution=export.pop("resolution","1920x1080"); template=resolve_template(track.get("preset",job.get("preset","01_clean_bars"))); target=Path(job["output_dir"])/(track.get("output_name") or (source.stem+output_extension(fmt))); options=ExportOptions.from_resolution(resolution,format=fmt,**{k:v for k,v in export.items() if k in {"fps","quality","renderer","width","height","ffmpeg_path","video_codec","include_audio","canvas_mode"}});
                    if track.get("set_audio_files"): return render_set(track["set_audio_files"],target,template,options,track.get("timeline_path"),progress_detail=progress_detail,cancel=lambda: manager.cancel_requested)
                    if track.get("segment_manifest") and fmt.lower()=="webm": return render_segmented_track(source,target,template,options,track["segment_manifest"],track["segment_root"],progress_detail=progress_detail,cancel=lambda: manager.cancel_requested)
                    return render_audio(source,target,template,options,progress_detail=progress_detail)
                self.runner=manager;result=manager.run(render_track,progress=lambda si,st,ti,tt,item:self.progress.emit(sum(x.total for x in manager.sets[:si-1])+ti,sum(x.total for x in manager.sets)),progress_detail=self.detail.emit,sleep_guard=SleepPrevention(sleep_enabled))
            self.done.emit(result)
        except Exception as exc:self.failed.emit(str(exc))
    def validate_tracks(self):
        folder=QFileDialog.getExistingDirectory(self,"Select folder with up to 15 tracks")
        if folder:self.start_task("validation",(folder,"validation_results/user_audio_validation.json",15))
    def closeEvent(self,event):
        self.stop_preview_worker()
        if self.reference_worker:self.reference_worker.cancel()
        if self.reference_thread and self.reference_thread.isRunning():
            self.reference_thread.requestInterruption();self.reference_thread.quit();self.reference_thread.wait(2000)
            if self.reference_thread.isRunning():self.reference_thread.terminate();self.reference_thread.wait(1000)
        for thread in self.findChildren(QThread):
            if thread.isRunning():thread.quit();thread.wait(2000)
            if thread.isRunning():thread.terminate();thread.wait(1000)
        super().closeEvent(event)
    def system_check(self):
        report=format_report(check_system());QMessageBox.information(self,"System Check",report)
    def cancel(self):
        if self.runner:self.runner.cancel()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); app=QApplication.instance(); families=set(QFontDatabase.families()); chosen=next((name for name in ("Malgun Gothic","Noto Sans CJK KR","Noto Sans","Segoe UI") if name in families), None); chosen and app.setFont(QFont(chosen,10)); self.translator=Translator("ko");self.queue_manager=QueueManager();self.app_settings=AppSettings();self.current_output_dir=str(self.app_settings.get("last_output_folder","") or "");self.setWindowTitle(f"Music Wave Studio v{get_version()}");self.resize(1500,900);self.audio_files=[];self.reference_images=[];self.reference_video=None;self.roi=None;self.template=load_template(resource_path("templates/01_clean_bars.json"));self.preview_engine=PreviewEngine();self.scheduler=FrameScheduler(24);self.current_time=0;self.thread=None;self.worker=None;self.preview_thread=None;self.preview_worker=None;self.preview_mailbox=None;self.reference_thread=None;self.reference_worker=None;self._syncing=False
        self.player=QMediaPlayer();self.audio_output=QAudioOutput();self.player.setAudioOutput(self.audio_output);self.player.positionChanged.connect(self._media_position);self.player.durationChanged.connect(self._media_duration)
        self.preview_timer=QTimer(self);self.preview_timer.setTimerType(Qt.PreciseTimer);self.preview_timer.setInterval(8);self.preview_timer.timeout.connect(self._tick);self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(90);self.debounce.timeout.connect(self.render_preview)
        root=QWidget();layout=QVBoxLayout(root);layout.addWidget(self._step_navigator());self.body_widget=QWidget();self.body_layout=QHBoxLayout(self.body_widget);layout.addWidget(self.body_widget,1);self.left_widget=self._left_panel();self.center_widget=self._center_panel();self.right_widget=self._right_panel();self.body_layout.addWidget(self.left_widget,2);self.body_layout.addWidget(self.center_widget,5);self.body_layout.addWidget(self.right_widget,3);self.progress_page=self._progress_page();self.body_layout.addWidget(self.progress_page,1);self.progress_page.hide();layout.addWidget(self._bottom_panel());self.setCentralWidget(root);self._apply_theme();self.refresh_templates();self.sync_controls();self._restore_settings();self._localize_existing();QTimer.singleShot(200,self._first_run_and_resume)
    def _left_panel(self):
        tabs=QTabWidget();media=QWidget();m=QVBoxLayout(media);self.audio_list=QListWidget();m.addWidget(QLabel("Audio Files"));m.addWidget(self.audio_list);row_audio=QHBoxLayout();button=QPushButton("Add Audio");button.clicked.connect(self.add_audio);folder_button=QPushButton(self.translator.tr("add_folder"));folder_button.clicked.connect(self.add_folder);row_audio.addWidget(folder_button);row_audio.addWidget(button);m.addLayout(row_audio);tabs.addTab(media,"Media")
        ref=QWidget();r=QVBoxLayout(ref);self.ref_list=QListWidget();r.addWidget(QLabel(self.translator.tr("reference_images")));r.addWidget(self.ref_list);row=QHBoxLayout()
        for text,fn in (("Add Image",self.add_reference),("Remove",self.remove_reference),("Clear",self.clear_reference)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        r.addLayout(row);self.reference_analyze_button=QPushButton(self.translator.tr("reference_analyze"));self.reference_analyze_button.clicked.connect(self.analyze_reference_images);r.addWidget(self.reference_analyze_button);self.reference_cancel_button=QPushButton(self.translator.tr("reference_cancel"));self.reference_cancel_button.clicked.connect(self.cancel_reference_analysis);self.reference_cancel_button.hide();r.addWidget(self.reference_cancel_button);self.reference_status=QLabel(self.translator.tr("reference_status"));r.addWidget(self.reference_status);roirow=QHBoxLayout();b=QPushButton(self.translator.tr("roi_draw"));b.clicked.connect(self.draw_roi);roirow.addWidget(b);b=QPushButton(self.translator.tr("roi_coordinate"));b.clicked.connect(self.set_roi);roirow.addWidget(b);b=QPushButton(self.translator.tr("roi_reset"));b.clicked.connect(self.reset_roi);roirow.addWidget(b);r.addLayout(roirow);self.video_label=QLabel(self.translator.tr("no_video"));r.addWidget(self.video_label);b=QPushButton(self.translator.tr("select_video"));b.clicked.connect(self.add_video);r.addWidget(b);b=QPushButton(self.translator.tr("analyze_motion"));b.clicked.connect(self.analyze_motion);r.addWidget(b);tabs.addTab(ref,"Reference")
        templates=QWidget();t=QVBoxLayout(templates);self.template_filter=QComboBox();self.template_filter.addItems(["\ucd94\ucc9c \uC2A4\ud0c0\uc77c","\uc804\uccb4 \uC2A4\ud0c0\uc77c","\uc2dc\ub2c8\uc5b4","Tokyo Chill","Jazz/Chanson","Modern"]);self.template_filter.currentTextChanged.connect(self.filter_templates);t.addWidget(self.template_filter);self.template_list=QListWidget();self.template_list.setViewMode(QListWidget.IconMode);self.template_list.setIconSize(QSize(180,72));self.template_list.setResizeMode(QListWidget.Adjust);self.template_list.setSpacing(8);self.template_list.itemClicked.connect(self.apply_gallery);t.addWidget(self.template_list);b=QPushButton("Save as My Template");b.clicked.connect(self.save_my_template);t.addWidget(b);tabs.addTab(templates,"파형 스타일");self.playlist_panel=PlaylistPanel();tabs.addTab(self.playlist_panel,"곡 목록");self.queue_panel=QueuePanel(self.queue_manager);self.queue_panel.startRequested.connect(self.start_queue);self.queue_panel.add_button.clicked.connect(self.add_to_queue);tabs.addTab(self.queue_panel,"예약 작업");self.left_tabs=tabs;return tabs
    def _center_panel(self):
        box=QWidget();v=QVBoxLayout(box);self.preview=QLabel("Add audio and click Analyze");self.preview.setMinimumSize(640,360);self.preview.setAlignment(Qt.AlignCenter);self.preview.setStyleSheet("background:#080B10;border:1px solid #283343");v.addWidget(self.preview,1);row=QHBoxLayout()
        for text,fn in (("▶ Play",self.play),("Ⅱ Pause",self.pause),("■ Stop",self.stop)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.timeline=QSlider(Qt.Horizontal);self.timeline.setRange(0,0);self.timeline.sliderMoved.connect(self.seek);row.addWidget(self.timeline,1);self.time_label=QLabel("00:00 / 00:00");row.addWidget(self.time_label);v.addLayout(row);return box
    def _right_panel(self):
        self.tabs=QTabWidget();self.tabs.setUsesScrollButtons(True);self.fields={};self.combos={};self.checks={};self.simple_controls=SimpleControls();self.simple_controls.changed.connect(self.simple_changed);self.tabs.addTab(self.simple_controls,"간편 설정");
        audio=("Bands",8,256,1),("Response",.1,3,.01),("Attack",0,1,.01),("Decay",0,1,.01),("Smoothing",0,.95,.01),("Onset Boost",0,2,.01),("Bass Weight",0,2,.01),("Mid Weight",0,2,.01),("High Weight",0,2,.01)
        design=("Width",.1,1,.01),("Height",.05,.9,.01),("Bar Width",.05,1,.01),("Gap",0,.95,.01),("Roundness",0,1,.01),("Opacity",0,1,.01)
        audio_widget=self._control_tab(audio,"audio");advanced=QFormLayout();self.analysis_mode=QComboBox();self.analysis_mode.addItems(["STANDARD","ADVANCED"]);self.fft_window=QComboBox();self.fft_window.addItems(["hann","hamming","blackman"]);self.spectrum_mapping=QComboBox();self.spectrum_mapping.addItems(["AUTO","LOG","PERCEPTUAL"]);audio_widget.layout().addRow("Analysis Mode",self.analysis_mode);audio_widget.layout().addRow("FFT Window",self.fft_window);audio_widget.layout().addRow("Spectrum Mapping",self.spectrum_mapping);self.tabs.addTab(audio_widget,"Audio");widget=self._control_tab(design,"design");form=widget.layout();self._combo(form,"Style",["bars","line","dot"],"renderer");self._combo(form,"Position",["top","center","bottom"],"position");self._check(form,"Mirror","mirror");self._color_button(form,"Main Color","color");self._check(form,"Gradient","gradient");self._color_button(form,"Gradient Start","gradient_start");self._color_button(form,"Gradient End","gradient_end");self.tabs.addTab(widget,"Design")
        effects=QWidget();f=QFormLayout(effects);self._check(f,"Glow","glow");self._number(f,"Glow Strength",0,2,.05,"glow_strength");self._number(f,"Glow Radius",0,40,1,"glow_radius");self._check(f,"Shadow","shadow");self.tabs.addTab(effects,"Effects");self.tabs.addTab(self._export_tab(),"Export");self.simple_controls.advanced.toggled.connect(self.toggle_advanced);self.toggle_advanced(False);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.tabs);return scroll
    def _control_tab(self,items,prefix):
        widget=QWidget();form=QFormLayout(widget)
        keys={"Bands":"bands","Response":"response","Attack":"attack","Decay":"decay","Smoothing":"smoothing","Onset Boost":"onset_boost","Bass Weight":"bass_weight","Mid Weight":"mid_weight","High Weight":"high_weight","Width":"width","Height":"height","Bar Width":"bar_width","Gap":"gap","Roundness":"roundness","Opacity":"opacity"}
        for label,lo,hi,step in items:self._number(form,label,lo,hi,step,keys[label])
        return widget
    def _number(self,form,label,lo,hi,step,key):
        control=QSpinBox() if step==1 else QDoubleSpinBox();control.setRange(lo,hi);control.setSingleStep(step);control.valueChanged.connect(self.controls_changed);self.fields[key]=control;form.addRow(label,control)
    def _combo(self,form,label,items,key):
        control=QComboBox();control.addItems(items);control.currentTextChanged.connect(self.controls_changed);self.combos[key]=control;form.addRow(label,control)
    def _check(self,form,label,key):
        control=QCheckBox();control.toggled.connect(self.controls_changed);self.checks[key]=control;form.addRow(label,control)
    def _color_button(self,form,label,key):
        button=QPushButton();button.clicked.connect(lambda:self.pick_color(key));self.fields[key]=button;form.addRow(label,button)
    def _export_tab(self):
        widget=QWidget();form=QFormLayout(widget);self.export_format=QComboBox();self.export_format.addItems(["mp4","mov","webm"]);self.export_format.setCurrentText("mp4");self.canvas_mode=QComboBox();self.canvas_mode.addItems(["빠른 투명 파형","전체 화면 투명 영상"]);self.canvas_mode.setCurrentIndex(0);self.resolution=QComboBox();self.resolution.addItems(["1920x1080","1080x1920","1080x1080","Custom"]);self.export_fps=QComboBox();self.export_fps.addItems(["24","30","60"]);self.export_fps.setCurrentIndex(0);self.renderer_choice=QComboBox();self.renderer_choice.addItems(["AUTO","GPU","CPU"]);self.quality=QComboBox();self.quality.addItems(["BALANCED","QUALITY","PREVIEW"]);self.skip_completed=QCheckBox();self.skip_completed.setChecked(True);self.prevent_sleep=QCheckBox();self.prevent_sleep.setChecked(True);self.custom_width=QSpinBox();self.custom_width.setRange(320,7680);self.custom_width.setValue(1920);self.custom_height=QSpinBox();self.custom_height.setRange(320,7680);self.custom_height.setValue(1080);self.ffmpeg_path=QLineEdit();self.ffmpeg_path.setPlaceholderText("System PATH (default)")
        self.output_location=QLabel(self.current_output_dir or "출력 폴더를 선택하세요");choose=QPushButton("폴더 변경");choose.clicked.connect(self.choose_output_dir);form.addRow("출력 위치",self.output_location);form.addRow("",choose)
        for label,control in (("저장 방식",self.canvas_mode),("Format",self.export_format),("Resolution",self.resolution),("Custom Width",self.custom_width),("Custom Height",self.custom_height),("FPS",self.export_fps),("Renderer",self.renderer_choice),("Quality",self.quality),("FFmpeg Path",self.ffmpeg_path),("Skip completed outputs",self.skip_completed),("Prevent sleep while rendering",self.prevent_sleep)):form.addRow(label,control)
        self.format_help=QLabel("MP4 H.264 · black background · CapCut Screen blend");self.export_format.currentTextChanged.connect(self._format_help);form.addRow(self.format_help);return widget
    def _bottom_panel(self):
        box=QWidget(); v=QVBoxLayout(box); self.bottom_actions=[]
        self.primary_action=QPushButton("이 스타일 사용하고 대기열에 추가"); self.primary_action.setMinimumHeight(52); self.primary_action.setStyleSheet("font-size:16px;font-weight:bold;background:#4A90E2;color:white"); self.primary_action.clicked.connect(self._primary_action); v.addWidget(self.primary_action)
        self.secondary_action=QPushButton("다른 세트 추가"); self.secondary_action.setMinimumHeight(40); self.secondary_action.clicked.connect(lambda:self.navigate_step(0)); v.addWidget(self.secondary_action)
        self.control_row=QHBoxLayout(); self.pause_button=QPushButton("일시정지"); self.resume_button=QPushButton("계속"); self.stop_button=QPushButton("작업 중단"); self.pause_button.clicked.connect(self.pause_queue); self.resume_button.clicked.connect(self.resume_queue); self.stop_button.clicked.connect(self.cancel); [self.control_row.addWidget(b) for b in (self.pause_button,self.resume_button,self.stop_button)]; v.addLayout(self.control_row)
        self.song_progress=QProgressBar(); self.song_progress.setMinimumHeight(28); self.song_progress.setFormat("현재 곡 %p%"); self.total_progress=QProgressBar(); self.total_progress.setMinimumHeight(28); self.total_progress.setFormat("전체 %p%"); v.addWidget(self.song_progress); v.addWidget(self.total_progress); self.status=QLabel("준비됨"); self.performance=QLabel("Renderer: ? | Preview FPS: ? | Cache: ? | Analysis: ?"); self.performance.hide(); v.addWidget(self.status); v.addWidget(self.performance)
        self._update_actions(); return box
    def _primary_action(self):
        if self.current_step==2: self.add_to_queue()
        elif self.current_step in (3,4): self.start_queue()
        elif self.current_step==0: self.add_folder()
    def _update_actions(self):
        if not hasattr(self,"primary_action"): return
        if getattr(self,"current_step",0)==2: self.primary_action.setText("이 스타일 사용하고 대기열에 추가"); self.primary_action.setEnabled(bool(self.audio_files))
        elif getattr(self,"current_step",0)==3: self.primary_action.setText("작업 시작"); self.primary_action.setEnabled(bool(self.queue_manager.sets))
        elif getattr(self,"current_step",0)==4: self.primary_action.setText("예약 작업 모두 시작"); self.primary_action.setEnabled(bool(self.queue_manager.sets))
        else: self.primary_action.setText("음원 폴더 선택"); self.primary_action.setEnabled(True)
        self.secondary_action.setVisible(getattr(self,"current_step",0) in (2,3)); self.pause_button.setVisible(False); self.resume_button.setVisible(False); self.stop_button.setVisible(False)
    def pause_queue(self):
        self.queue_manager.request_pause(); self.pause_button.setVisible(False); self.resume_button.setVisible(True); self.status.setText("작업이 일시정지되었습니다.")
    def resume_queue(self):
        self.queue_manager.resume(); self.pause_button.setVisible(True); self.resume_button.setVisible(False); self.status.setText("작업을 계속합니다.")
    def _progress_page(self):
        page=QWidget();v=QVBoxLayout(page);self.progress_title=QLabel("\uc601\uc0c1 \ub9cc\ub4dc\ub294 \uc911");self.progress_title.setStyleSheet("font-size:28px;font-weight:bold");v.addWidget(self.progress_title);self.progress_detail_label=QLabel("\uc791\uc5c5 \uc900\ube44 \uc911...");self.progress_detail_label.setStyleSheet("font-size:18px");v.addWidget(self.progress_detail_label);self.progress_elapsed=QLabel("경과 00:00    현재 곡 남은 시간 --:--    전체 남은 시간 --:--");v.addWidget(self.progress_elapsed);row=QHBoxLayout();skip=QPushButton("현재 곡 건너뛰기");stop=QPushButton("전체 작업 중지");stop.clicked.connect(self.cancel);row.addWidget(skip);row.addWidget(stop);v.addLayout(row);return page
    def _show_progress_page(self,visible=True):
        for widget in (self.left_widget,self.center_widget,self.right_widget):widget.setVisible(not visible)
        self.progress_page.setVisible(visible);self.performance.setVisible(False if visible else self.simple_controls.advanced.isChecked())

    def _first_run_and_resume(self):
        if os.environ.get("MWS_SMOKE_TEST")=="1":return
        if not bool(self.app_settings.get("first_run_done",False)):
            QMessageBox.information(self,"Music Wave Studio에 오신 것을 환영합니다.","1. 음원을 넣습니다.\n2. 파형 스타일을 고릅니다.\n3. 미리봅니다.\n4. 저장 형식을 고릅니다.\n5. 만들기를 누릅니다.")
            self.app_settings.set("first_run_done",True)
        if self.queue_manager.sets:
            answer=QMessageBox.question(self,"이전 예약 작업","이전 예약 작업이 있습니다. 이어서 실행할까요?",QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel)
            if answer==QMessageBox.Yes:self.start_queue()
            elif answer==QMessageBox.Cancel:self.queue_manager.clear();self.queue_panel.refresh()
    def _queue_completion(self,result):
        self._show_progress_page(False);self.navigate_step(4);self.status.setText(f"대기열 작업 완료. 성공 {result.tracks_success}곡 / 실패 {result.tracks_failed}곡")
    def _step_navigator(self):
        widget=QWidget();layout=QHBoxLayout(widget);self.step_labels=[]
        for index,key in enumerate(("step1","step2","step3","step4","step5")):
            button=QPushButton(self.translator.tr(key));button.setCheckable(True);button.setMinimumHeight(42);button.clicked.connect(lambda _checked=False,i=index:self.navigate_step(i));layout.addWidget(button);self.step_labels.append(button)
        self._set_step_visual(0);return widget
    def _set_step_visual(self,index):
        self.current_step=index
        for position,button in enumerate(self.step_labels):
            button.setChecked(position==index);button.setProperty("completed",position<index);button.style().unpolish(button);button.style().polish(button)
    def navigate_step(self,index):
        index=max(0,min(4,int(index)));self._set_step_visual(index); self._update_actions()
        if index==0:self.left_tabs.setCurrentIndex(0)
        elif index==1:self.left_tabs.setCurrentIndex(2)
        elif index==2:self.left_tabs.setCurrentIndex(0)
        elif index==3:self.left_tabs.setCurrentIndex(4)
        else:self.left_tabs.setCurrentIndex(4)
    def _localize_existing(self):
        pairs={"Media":"음원","Audio Files":"음원","Audio":"음악 반응","Reference":"참고 파형","Design":"디자인","Queue":"예약 작업","Playlist":"곡 목록","Templates":"파형 스타일","Effects":"효과","Export":"저장 설정","Add Audio":"음원 추가","Add Image":"이미지 추가","Remove":"삭제","Clear":"전체 지우기","Auto Analyze Images":"참고 이미지 분석","Draw ROI":"ROI 선택","Coordinate ROI":"ROI 좌표 입력","Reset ROI":"ROI 초기화","Analyze Motion":"움직임 분석","Save as My Template":"내 스타일로 저장","Play":"재생","Pause":"일시정지","Stop":"정지","Format":"출력 형식","Resolution":"해상도","FPS":"프레임 속도","Renderer":"렌더 방식","Quality":"품질","Ready":"\uc900\ube44\ub428"}
        mapping=pairs if self.translator.language=="ko" else {value:key for key,value in pairs.items()}
        for widget in self.findChildren(QWidget):
            if hasattr(widget,"text") and callable(widget.text):
                try:
                    value=widget.text()
                    if value in mapping:widget.setText(mapping[value])
                except (RuntimeError,TypeError):pass
        for tabs in self.findChildren(QTabWidget):
            for index in range(tabs.count()):
                value=tabs.tabText(index)
                if value in mapping:tabs.setTabText(index,mapping[value])
    def _set_language(self,language):
        self.translator.set_language(language);self._localize_existing()
        for label,key in zip(self.step_labels,("step1","step2","step3","step4","step5")):label.setText(self.translator.tr(key))
    def toggle_advanced(self,visible):
        for index in range(1,self.tabs.count()):self.tabs.setTabVisible(index,visible)
        self.simple_controls.advanced.setText("간편 설정으로 돌아가기" if visible else self.translator.tr("advanced"))
    def simple_changed(self,values):
        self.template["height"]={"작게":.14,"보통":.22,"크게":.34}.get(values.get("movement"),self.template.get("height",.22))
        self.template["response"]={"느리게":.8,"자연스럽게":1.25,"빠르게":1.9}.get(values.get("response"),1.25)
        self.template["smoothing"]={"잔잔하게":.55,"기본":.15,"선명하게":.02}.get(values.get("smooth"),.15)
        self.template["glow"] = values.get("glow")!="없음";self.template["glow_strength"]={"없음":0,"약하게":.25,"보통":.55,"강하게":.9}.get(values.get("glow"),.55)
        self.template["bass_weight"]={"약하게":.6,"기본":1.0,"강하게":1.5}.get(values.get("bass"),1.0);self.template["high_weight"]={"약하게":.6,"기본":1.0,"강하게":1.5}.get(values.get("treble"),1.0)
        self.sync_controls();self.debounce.start()
    def _audio_duration(self,path):
        try:
            with wave.open(str(path),"rb") as handle:return handle.getnframes()/max(handle.getframerate(),1)
        except Exception:return 0.0
    def add_to_queue(self):
        if not self.audio_files:self.status.setText("음원 폴더를 먼저 선택하세요."); return False
        out=self.ensure_output_dir()
        if not out:return False
        snapshot=self.build_current_job_snapshot();name=f"{datetime.date.today().isoformat()}_{snapshot['template'].get('name','Waveform')}"
        tracks=[]
        export_settings={"format":snapshot["options"].format,"resolution":"OVERLAY" if snapshot["options"].canvas_mode=="overlay" else self.resolution.currentText(),"width":snapshot["options"].width,"height":snapshot["options"].height,"canvas_mode":snapshot["options"].canvas_mode,"fps":snapshot["options"].fps,"quality":snapshot["options"].quality,"renderer":snapshot["options"].renderer,"ffmpeg_path":snapshot["options"].ffmpeg_path,"video_codec":snapshot["options"].video_codec,"include_audio":snapshot["options"].include_audio,"crf":snapshot["options"].crf}
        durations=[self._audio_duration(path) for path in snapshot["audio_files"]]
        set_duration=sum(durations)
        source_folder=Path(snapshot["audio_files"][0]).parent if snapshot["audio_files"] else Path(out)
        set_name=source_folder.name or "SET01"
        output_name=f"{set_name}_WAVE{output_extension(snapshot["options"].format)}"
        timeline_path=str(Path(out)/(Path(output_name).stem+"_timeline.json"))
        tracks.append({"audio":snapshot["audio_files"][0],"set_audio_files":list(snapshot["audio_files"]),"preset":snapshot["template"].get("name","01_clean_bars"),"format":snapshot["options"].format,"duration":set_duration,"output_name":output_name,"timeline_path":timeline_path,"status":"pending"})
        job=JobSet(name=name,tracks=tracks,preset=snapshot["template"].get("name","01_clean_bars"),export=export_settings,output_dir=out)
        try:self.queue_manager.add(job);self.queue_panel.refresh();self.navigate_step(3);self.left_tabs.setCurrentWidget(self.queue_panel);self.status.setText(f"예약 작업에 추가됨: {len(self.queue_manager.sets)} / 5");return True
        except ValueError as exc:self.status.setText(str(exc));QMessageBox.warning(self,"예약 작업",str(exc));return False
    def start_queue(self):
        if not self.queue_manager.sets:return
        checks=self.queue_manager.preflight(check_template=resolve_template);bad=[item for item in checks if not item["ready"]]
        if bad:
            QMessageBox.warning(self,"실행 전 검사","일부 예약 작업을 시작할 수 없습니다. 예약 작업 탭에서 실행 전 검사 결과를 확인하세요.")
            return
        self.navigate_step(4);self._show_progress_page(True);self.primary_action.setVisible(False);self.secondary_action.setVisible(False);self._render_started_at=time.perf_counter(); self.pause_button.setVisible(True); self.stop_button.setVisible(True);self.progress_title.setText("\uc601\uc0c1 \ub9cc\ub4dc\ub294 \uc911");self.progress_detail_label.setText("\uc791\uc5c5 \uc900\ube44 \uc911...");self.start_task("queue",(self.queue_manager,self.prevent_sleep.isChecked()));self.status.setText("FFmpeg \uc2dc\uc791 \uc911...")
    def _apply_theme(self):self.setStyleSheet("QWidget{background:#11151C;color:#F4F7FA;font-size:13px}QGroupBox{border:1px solid #394657;border-radius:5px;margin-top:8px;padding-top:10px}QGroupBox::title{color:#F4F7FA}QPushButton,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit{background:#222B37;color:#F4F7FA;border:1px solid #394657;padding:7px;border-radius:4px;min-height:24px}QPushButton:hover,QComboBox:hover{background:#2E4663;border-color:#4A90E2}QPushButton:pressed,QPushButton:checked{background:#4A90E2;color:white}QTabWidget::pane{background:#181E27;border:1px solid #394657}QTabBar::tab{background:#181E27;color:#B7C0CB;padding:10px 14px;min-height:20px}QTabBar::tab:selected{background:#4A90E2;color:#FFFFFF}QTabBar::tab:hover{background:#2E4663;color:#FFFFFF}QListWidget,QTableWidget{background:#181E27;color:#F4F7FA;border:1px solid #394657}QHeaderView::section{background:#222B37;color:#F4F7FA;padding:6px}QSlider::groove:horizontal{background:#394657;height:6px}QSlider::handle:horizontal{background:#4A90E2;width:14px;margin:-5px 0}QProgressBar{background:#222B37;color:#F4F7FA;border:1px solid #394657;text-align:center;min-height:28px;font-size:14px;font-weight:bold}QProgressBar::chunk{background:#4A90E2}QToolTip{background:#222B37;color:#F4F7FA;border:1px solid #4A90E2}")
    def _default_wave_dir(self):
        if not self.audio_files:return ""
        return str(Path(self.audio_files[0]).resolve().parent / "wave")
    def add_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"음원 폴더 선택")
        if not folder:return False
        extensions={".wav",".mp3",".flac",".m4a",".aac",".ogg",".opus"}
        files=sorted((str(path) for path in Path(folder).iterdir() if path.is_file() and path.suffix.lower() in extensions),key=lambda value:Path(value).name.casefold())
        if not files:return False
        self.audio_files=files;self.audio_list.clear();self.audio_list.addItems([Path(path).name for path in files]);self.set_output_dir(str(Path(folder)/"wave"));self.navigate_step(1);self.analyze_audio();return True
    def render_detail(self,event):
        percent=float(event.get("percent",0));self.song_progress.setValue(int(percent))
        track=event.get("track_index",1);track_total=event.get("track_total",len(self.audio_files) or 1);set_index=event.get("set_index",1);set_total=event.get("set_total",1);overall=((set_index-1)+(track-1+percent/100.0)/max(track_total,1))/max(set_total,1)*100.0;self.total_progress.setValue(int(max(0,min(100,overall))))
        name=Path(self.audio_files[track-1]).name if self.audio_files and 0<track<=len(self.audio_files) else ""
        fps=float(event.get("fps",0));elapsed=max(0.0,time.perf_counter()-getattr(self,"_render_started_at",time.perf_counter()));track_duration=self._audio_duration(self.audio_files[track-1]) if self.audio_files and 0<track<=len(self.audio_files) else 0.0;remain=(track_duration*(100.0-percent)/100.0)/(max(percent/100.0,0.01)) if track_duration and percent>1 else 0.0;eta=f"{int(remain)//60:02d}:{int(remain)%60:02d}" if remain else "계산 중";self.progress_elapsed.setText(f"경과 {int(elapsed)//60:02d}:{int(elapsed)%60:02d}    현재 곡 남은 시간 {eta}    전체 남은 시간 {eta}");self.progress_detail_label.setText(f"세트 {set_index} / {set_total}\n현재 곡 {track} / {track_total}\n{name}\n현재 곡 진행률 {percent:.0f}%\n렌더 속도 {fps:.1f} fps");self.status.setText("\\ub80c\\ub354 \\uc9c4\\ud589 \\uc911...")
    def add_audio(self):
        files,_=QFileDialog.getOpenFileNames(self,"Audio files","","Audio (*.wav *.mp3 *.flac *.m4a *.ogg)");self.audio_files.extend(x for x in files if x not in self.audio_files);self.audio_list.clear();self.audio_list.addItems(self.audio_files)
        if self.audio_files:
            self.player.setSource(QUrl.fromLocalFile(self.audio_files[0]));self.set_output_dir(str(Path(self.audio_files[0]).resolve().parent / "wave"));self.navigate_step(1);self.analyze_audio()
    def add_reference(self):
        files,_=QFileDialog.getOpenFileNames(self,"Reference images","","Images (*.png *.jpg *.jpeg *.webp)");
        for path in files:
            if path not in self.reference_images and len(self.reference_images)<5:self.reference_images.append(path)
        self.ref_list.clear();self.ref_list.addItems(self.reference_images)
    def remove_reference(self):
        row=self.ref_list.currentRow();
        if row>=0:self.reference_images.pop(row);self.ref_list.takeItem(row)
    def clear_reference(self):self.reference_images.clear();self.ref_list.clear();self.roi=None
    def add_video(self):
        path,_=QFileDialog.getOpenFileName(self,"Reference video","","Video (*.mp4 *.mov *.webm *.mkv)");self.reference_video=path or None;self.video_label.setText(Path(path).name if path else self.translator.tr("no_video"))
    def draw_roi(self):
        if not self.reference_images:return
        row=self.ref_list.currentRow();path=self.reference_images[row if row>=0 else 0];dialog=ROIDialog(path,self)
        if dialog.exec():
            roi=dialog.roi()
            if roi:self.roi=roi;self.status.setText(f"ROI: {roi}");self.analyze_reference_images()
    def reset_roi(self):self.roi=None;self.status.setText("ROI reset; full image analysis active")
    def set_roi(self):
        text,ok=QInputDialog.getText(self,"Manual ROI","x, y, width, height")
        if ok:
            try:self.roi=tuple(map(int,text.replace(" ","").split(",")));assert len(self.roi)==4;self.status.setText(f"ROI: {self.roi}")
            except Exception:self.roi=None;QMessageBox.warning(self,"ROI","Use x,y,width,height")
    def analyze_reference_images(self):
        if self.reference_thread and self.reference_thread.isRunning():
            self.reference_status.setText(self.translator.tr("reference_start_failed"));return
        if not self.reference_images:return
        self.reference_analyze_button.setEnabled(False);self.reference_cancel_button.show();self.reference_status.setText(self.translator.tr("reference_preparing"))
        self.reference_thread=QThread(self);self.reference_worker=ReferenceAnalysisWorker(list(self.reference_images),self.roi);self.reference_worker.moveToThread(self.reference_thread);self.reference_thread.started.connect(self.reference_worker.run);self.reference_worker.stage_changed.connect(lambda name,current,total:self.reference_status.setText(f"{current} / {total} {name}"));self.reference_worker.result_ready.connect(self.apply_reference);self.reference_worker.failed.connect(self.reference_analysis_failed);self.reference_worker.cancelled.connect(lambda:self.reference_status.setText(self.translator.tr("reference_cancelled")));self.reference_worker.finished.connect(self.reference_analysis_finished);self.reference_worker.finished.connect(self.reference_thread.quit);self.reference_thread.finished.connect(self.reference_worker.deleteLater);self.reference_thread.finished.connect(self.reference_thread.deleteLater);self.reference_thread.start()
    def cancel_reference_analysis(self):
        if self.reference_worker:self.reference_worker.cancel()
    def reference_analysis_failed(self,message):
        self.reference_status.setText(self.translator.tr("reference_failed"));self.status.setText(self.translator.tr("reference_failed"))
    def reference_analysis_finished(self):
        self.reference_analyze_button.setEnabled(True);self.reference_cancel_button.hide();self.reference_worker=None
    def analyze_motion(self):
        if self.reference_video:self.start_task("video",(self.reference_video,self.roi,10))
    def apply_reference(self,result):
        before=copy.deepcopy(self.template);updated=copy.deepcopy(self.template);updated.update(result);self.template=updated;self.sync_controls();self.debounce.start();self.reference_status.setText(self.translator.tr("reference_complete"));self.navigate_step(2)
    def refresh_templates(self):
        self.template_entries=[]
        for path,data in list_templates(resource_path("templates"),"my_templates"):
            self.template_entries.append((path,data))
        self.filter_templates(self.template_filter.currentText() if hasattr(self,"template_filter") else "\ucd94\ucc9c \uC2A4\ud0c0\uc77c")
    def filter_templates(self,mode="전체 스타일"):
        if not hasattr(self,"template_list"): return
        self.template_list.clear()
        recommended={"01_clean_bars","10_warm_cream_line","18_tokyo_neon","28_paris_thin_line","31_blue_jazz","42_glass_spectrum"}
        for path,data in getattr(self,"template_entries",[]):
            category=str(data.get("category","")).lower(); ident=str(data.get("id",path.stem))
            if mode=="\ucd94\ucc9c \uC2A4\ud0c0\uc77c" and ident not in recommended: continue
            if mode=="\uc2dc\ub2c8\uc5b4" and category!="senior": continue
            if mode=="Tokyo Chill" and category!="tokyo_chill": continue
            if mode=="Jazz/Chanson" and category!="jazz_chanson": continue
            if mode=="Modern" and category!="modern": continue
            label=data.get("name_ko",data.get("name_en",data.get("name","Style")))
            item=QListWidgetItem(str(label));item.setToolTip(f"{data.get('name_en',data.get('name',''))} | {data.get('category','')}");item.setData(Qt.UserRole,str(path));thumb_path,_=get_thumbnail(dict(data,glow=False));item.setIcon(QIcon(str(thumb_path)));self.template_list.addItem(item)
    def apply_gallery(self,item):self.template=load_template(item.data(Qt.UserRole));self.sync_controls();self.debounce.start();self.navigate_step(2)
    def save_my_template(self):
        name,ok=QInputDialog.getText(self,"Save Template","Template name")
        if ok and name.strip():self.template["name"]=name.strip();safe="".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip());save_template(Path("my_templates")/(safe+".json"),self.template);self.refresh_templates();self.status.setText("Saved to My Templates")
    def sync_controls(self):
        self._syncing=True
        for key,control in self.fields.items():
            value=self.template.get(key)
            if isinstance(control,QPushButton):control.setText(str(value));control.setStyleSheet(f"background:{value};color:#111" if value else "")
            elif value is not None:control.setValue(value)
        for key,c in self.combos.items():c.setCurrentText(str(self.template.get(key,c.currentText())))
        for key,c in self.checks.items():c.setChecked(bool(self.template.get(key,False)))
        self._syncing=False
    def controls_changed(self,*_):
        if self._syncing:return
        for key,c in self.fields.items():
            if not isinstance(c,QPushButton):self.template[key]=c.value()
        for key,c in self.combos.items():self.template[key]=c.currentText()
        for key,c in self.checks.items():self.template[key]=c.isChecked()
        bands_changed=self.preview_engine.features is not None and int(self.template.get("bands",64))!=int(self.preview_engine.features["spectrum"].shape[1])
        if bands_changed:self.status.setText("Bands are resampled in the preview worker without FFT")
        self.debounce.start()
    def pick_color(self,key):
        color=QColorDialog.getColor(QColor(self.template.get(key,"#FFFFFF")),self)
        if color.isValid():self.template[key]=color.name().upper();self.sync_controls();self.debounce.start()
    def analyze_audio(self):
        if self.audio_files:self.start_task("analysis",(self.audio_files[0],AnalysisSettings(fps=24,bands=int(self.template["bands"]),fft_window=self.fft_window.currentText(),spectrum_mapping=self.spectrum_mapping.currentText())))
    def start_task(self,kind,payload):
        if self.thread and self.thread.isRunning():return
        self.thread=QThread();self.worker=TaskWorker(kind,payload);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.status.connect(self.status.setText);self.worker.progress.connect(lambda a,b:self.total_progress.setValue(int(a*100/b)));self.worker.detail.connect(self.render_detail);self.worker.failed.connect(self.task_failed);self.worker.done.connect(lambda result:self.task_done(kind,result));self.worker.done.connect(self.thread.quit);self.worker.failed.connect(self.thread.quit);self.thread.start();self.status.setText(f"{kind.title()} running…")
    def task_done(self,kind,result):
        if kind=="analysis":
            features,hit,elapsed=result;self.preview_engine.features=features;self.navigate_step(2);self.preview_engine.template=dict(self.template);self.preview_engine.metrics.cache_hit=hit;self.preview_engine.metrics.analysis_seconds=elapsed;self.timeline.setMaximum(int(float(features["duration"][0])*1000));self.start_preview_worker(features);self.render_preview()
        elif kind in ("images","video"):self.apply_reference(result)
        elif kind=="validation":self.status.setText(f"Validation: {result['successful_tracks']}/{result['total_tracks']} ready; report saved");return
        elif kind=="playlist":self.status.setText(f"Playlist complete: {result['success']} success, {result['failed']} failed");return
        elif kind=="queue":self.queue_panel.refresh();self._queue_completion(result);return
        else:
            self.total_progress.setValue(100)
            successful=[item for item in result if item.get("status")=="success"]
            if successful:
                last=successful[-1];self.performance.setText(f"Renderer: {last.get('renderer','—')} | Generation: {last.get('frame_generation_fps',0):.1f} fps | Output: {last.get('average_fps',0):.1f} fps | Bottleneck: {last.get('bottleneck','—')} | Cache: {'HIT' if last.get('cache_hit') else 'MISS'}")
        self.status.setText("Ready")
    def task_failed(self,error):self.status.setText("Failed: "+error)
    def start_preview_worker(self,features):
        self.stop_preview_worker();self.preview_mailbox=LatestFrameMailbox();self.preview_thread=QThread(self);self.preview_worker=PreviewRenderWorker(features,self.template,self.renderer_choice.currentText(),self.preview_mailbox);self.preview_worker.moveToThread(self.preview_thread);self.preview_thread.started.connect(self.preview_worker.start);self.preview_worker.frameReady.connect(self.preview_frame_ready);self.preview_worker.ready.connect(lambda name:setattr(self.preview_engine.metrics,"renderer",name));self.preview_worker.failed.connect(self.task_failed);self.preview_worker.stopped.connect(self.preview_thread.quit);self.preview_thread.start()
    def stop_preview_worker(self):
        if self.preview_thread and self.preview_thread.isRunning() and self.preview_worker:
            QMetaObject.invokeMethod(self.preview_worker,"stop",Qt.BlockingQueuedConnection);self.preview_thread.quit();self.preview_thread.wait(3000)
        self.preview_thread=None;self.preview_worker=None;self.preview_mailbox=None
    def render_preview(self):
        if self.preview_mailbox is not None:self.preview_mailbox.submit(self.current_time,self.template)
    def preview_frame_ready(self,image,seconds,metrics):
        if abs(seconds-self.current_time)>.25:return
        h,w=image.shape[:2];q=QImage(image.data,w,h,image.strides[0],QImage.Format_RGBA8888).copy();self.preview.setPixmap(QPixmap.fromImage(q).scaled(self.preview.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation));timing=self.scheduler.metrics;self.preview_engine.metrics.fps=metrics["fps"];self.preview_engine.metrics.renderer=metrics["renderer"];self.performance.setText(f"Renderer: {metrics['renderer']} | Preview FPS: {metrics['fps']:.1f} | Replaced: {metrics['replaced']} | Dropped: {timing.dropped_frames} | Drift: {timing.max_drift*1000:.1f} ms | Cache: {'HIT' if self.preview_engine.metrics.cache_hit else 'MISS'}")
    def play(self):
        if self.preview_engine.features is not None:self.scheduler.reset(self.player.position()/1000,time.perf_counter());self.player.play();self.preview_timer.start()
    def pause(self):self.player.pause();self.preview_timer.stop()
    def stop(self):self.player.stop();self.preview_timer.stop();self.current_time=0;self.scheduler.reset(0,time.perf_counter());self.preview_engine.seek(0);self.timeline.setValue(0);self.render_preview()
    def seek(self,milliseconds):self.player.setPosition(milliseconds);self.current_time=milliseconds/1000;self.scheduler.seek(self.current_time,time.perf_counter());self.preview_engine.seek(self.current_time);self.render_preview()
    def _tick(self):
        self.current_time=self.player.position()/1000;now=time.perf_counter()
        if self.scheduler.should_render(self.current_time,now):self.render_preview()
    def _media_position(self,value):self.timeline.setValue(value);self.time_label.setText(f"{format_time(value/1000)} / {format_time(self.player.duration()/1000)}")
    def _media_duration(self,value):self.timeline.setMaximum(value)
    def _format_help(self,value):self.format_help.setText({"mp4":"MP4 H.264 · black background · CapCut Screen blend","webm":"WebM VP9 · transparent alpha","mov":"MOV PNG Alpha · CapCut 권장"}[value])
    def set_output_dir(self,path):
        self.current_output_dir=str(Path(path).resolve()) if path else ""
        if self.current_output_dir:
            self.app_settings.set("last_output_folder",self.current_output_dir)
            if hasattr(self,"output_location"):self.output_location.setText(self.current_output_dir)
    def choose_output_dir(self):
        selected=QFileDialog.getExistingDirectory(self,"출력 폴더 선택",self.current_output_dir or "output")
        if selected:self.set_output_dir(selected)
        return bool(selected)
    def ensure_output_dir(self):
        path=self.current_output_dir
        if path and Path(path).is_dir():return path
        automatic=self._default_wave_dir()
        if automatic:
            Path(automatic).mkdir(parents=True,exist_ok=True);self.set_output_dir(automatic);return automatic
        return self.current_output_dir if self.choose_output_dir() else ""
    def build_current_job_snapshot(self):
        output=self.current_output_dir
        if self.canvas_mode.currentIndex()==0 and self.export_format.currentText()=="mp4":width,height=720,180
        elif self.canvas_mode.currentIndex()==0 and self.export_format.currentText() in ("webm","mov"):width,height=960,240
        elif self.resolution.currentText()=="Custom":width,height=self.custom_width.value(),self.custom_height.value()
        else:width,height=map(int,self.resolution.currentText().split("x"))
        fmt=self.export_format.currentText(); overlay=self.canvas_mode.currentIndex()==0; codec="h264" if fmt=="mp4" and overlay else ("png" if fmt=="mov" and overlay else "auto"); include_audio=False if overlay else True; options=ExportOptions(width,height,int(self.export_fps.currentText()),self.quality.currentText(),self.renderer_choice.currentText(),fmt,self.ffmpeg_path.text() or None,"overlay" if overlay else "full",codec,include_audio,27 if fmt=="mp4" and overlay else None)
        return {"audio_files":list(self.audio_files),"template":copy.deepcopy(self.template),"options":options,"output_dir":output,"skip_completed":self.skip_completed.isChecked()}
    def render(self):
        return self.render_now()
    def render_now(self):
        if not self.audio_files:
            self.navigate_step(0);return False
        out=self.ensure_output_dir()
        if not out:
            self.navigate_step(3);return False
        self.set_output_dir(out);space=disk_warning(out)
        if space["warning"] and QMessageBox.warning(self,"Low Disk Space",f"Only {space['free']/1024**3:.1f} GB is available. Continue?",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return False
        snapshot=self.build_current_job_snapshot();self.last_job_snapshot=snapshot;self.start_task("render",(snapshot["audio_files"],snapshot["output_dir"],snapshot["template"],snapshot["options"],snapshot["skip_completed"]));self.navigate_step(4);return True
    def render_playlist(self):
        project=self.playlist_panel.project
        if not project.tracks:return
        out=QFileDialog.getExistingDirectory(self,"Playlist output directory",project.output_dir or "output")
        if not out:return
        resolution=self.resolution.currentText() if self.resolution.currentText()!="Custom" else "custom"
        export={"resolution":resolution,"width":self.custom_width.value(),"height":self.custom_height.value(),"fps":int(self.export_fps.currentText()),"renderer":self.renderer_choice.currentText(),"quality":self.quality.currentText(),"ffmpeg_path":self.ffmpeg_path.text() or None}
        tracks=[{"audio":track.source_path,"preset":track.preset,"format":track.output_format,"export":track.export_override} for track in project.tracks if track.status!="completed" or not self.skip_completed.isChecked()]
        self.start_task("playlist",{"contract_version":1,"tracks":tracks,"output_dir":out,"format":self.export_format.currentText(),"export":export})
    def validate_tracks(self):
        folder=QFileDialog.getExistingDirectory(self,"Select folder with up to 15 tracks")
        if folder:self.start_task("validation",(folder,"validation_results/user_audio_validation.json",15))
    def _restore_settings(self):
        self.renderer_choice.setCurrentText(str(self.app_settings.get('renderer_mode','AUTO')))
        self.quality.setCurrentText(str(self.app_settings.get('quality','BALANCED')))
        self.resolution.setCurrentText(str(self.app_settings.get('resolution','1920x1080')))
        self.export_fps.setCurrentText(str(self.app_settings.get('fps','30')))
        self.ffmpeg_path.setText(str(self.app_settings.get("ffmpeg_path","") or ""));self.current_output_dir=str(self.app_settings.get("last_output_folder","") or "");self.app_settings.restore_window(self)
    def closeEvent(self,event):
        self.app_settings.set("renderer_mode",self.renderer_choice.currentText());self.app_settings.set("quality",self.quality.currentText());self.app_settings.set("resolution",self.resolution.currentText());self.app_settings.set("fps",self.export_fps.currentText());self.app_settings.set("ffmpeg_path",self.ffmpeg_path.text());self.app_settings.save_window(self);self.stop_preview_worker();super().closeEvent(event)
    def system_check(self):
        report=format_report(check_system());QMessageBox.information(self,"System Check",report)
    def cancel(self):
        if self.worker:self.worker.cancel();self.status.setText("Cancelling…")
