from __future__ import annotations
import copy,time,datetime,os,subprocess
from pathlib import Path
import numpy as np
from PySide6.QtCore import QObject,QMetaObject,QThread,QTimer,QUrl,Signal,Slot,Qt
from PySide6.QtGui import QColor,QIcon,QImage,QPixmap
from PySide6.QtMultimedia import QAudioOutput,QMediaPlayer
from PySide6.QtWidgets import (QApplication,QCheckBox,QColorDialog,QComboBox,QFileDialog,QFormLayout,QGroupBox,QHBoxLayout,QInputDialog,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMainWindow,QMessageBox,QProgressBar,QPushButton,QScrollArea,QSlider,QSpinBox,QDoubleSpinBox,QTabWidget,QVBoxLayout,QWidget)
from audio.analyzer import AnalysisSettings,analyze_file
from core.paths import resource_path
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

class TaskWorker(QObject):
    done=Signal(object);failed=Signal(str);status=Signal(str);progress=Signal(int,int)
    def __init__(self,kind,payload):super().__init__();self.kind=kind;self.payload=payload;self.runner=None
    @Slot()
    def run(self):
        try:
            if self.kind=="analysis":
                started=time.perf_counter(); features,hit=analyze_file(self.payload[0],self.payload[1] if isinstance(self.payload[1],AnalysisSettings) else AnalysisSettings(fps=24,bands=self.payload[1]),logger=self.status.emit); result=(features,hit,time.perf_counter()-started)
            elif self.kind=="render":
                files,out,template,options,skip_completed=self.payload;self.runner=BatchRunner();result=self.runner.run(files,out,template,options,skip_completed=skip_completed,progress=lambda a,b,e:(self.progress.emit(a,b),self.status.emit(f"ETA {e:.0f}s")))
            elif self.kind=="images":result=analyze_images(*self.payload)
            elif self.kind=="video":result=analyze_video(*self.payload)
            elif self.kind=="validation":result=validate_audio_folder(*self.payload)
            elif self.kind=="playlist":result=run_job(self.payload)
            elif self.kind=="queue":
                manager,sleep_enabled=self.payload
                def render_track(track,job):
                    source=Path(track.get("audio",track.get("source_path",""))); fmt=track.get("format",job.get("export",{}).get("format","webm")); export={**job.get("export",{}),**track.get("export",{})}; resolution=export.pop("resolution","1920x1080"); template=resolve_template(track.get("preset",job.get("preset","01_clean_bars"))); target=Path(job["output_dir"])/(source.stem+output_extension(fmt)); options=ExportOptions.from_resolution(resolution,format=fmt,**{k:v for k,v in export.items() if k in {"fps","quality","renderer","width","height","ffmpeg_path"}}); return render_audio(source,target,template,options)
                self.runner=manager;result=manager.run(render_track,progress=lambda si,st,ti,tt,item:self.progress.emit(sum(x.total for x in manager.sets[:si-1])+ti,sum(x.total for x in manager.sets)),sleep_guard=SleepPrevention(sleep_enabled))
            self.done.emit(result)
        except Exception as exc:self.failed.emit(str(exc))
    def validate_tracks(self):
        folder=QFileDialog.getExistingDirectory(self,"Select folder with up to 15 tracks")
        if folder:self.start_task("validation",(folder,"validation_results/user_audio_validation.json",15))
    def closeEvent(self,event):
        self.stop_preview_worker();super().closeEvent(event)
    def system_check(self):
        report=format_report(check_system());QMessageBox.information(self,"System Check",report)
    def cancel(self):
        if self.runner:self.runner.cancel()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.translator=Translator("ko");self.queue_manager=QueueManager();self.setWindowTitle("Music Wave Studio");self.resize(1500,900);self.audio_files=[];self.reference_images=[];self.reference_video=None;self.roi=None;self.template=load_template(resource_path("templates/01_clean_bars.json"));self.preview_engine=PreviewEngine();self.scheduler=FrameScheduler(24);self.current_time=0;self.thread=None;self.worker=None;self.preview_thread=None;self.preview_worker=None;self.preview_mailbox=None;self._syncing=False
        self.player=QMediaPlayer();self.audio_output=QAudioOutput();self.player.setAudioOutput(self.audio_output);self.player.positionChanged.connect(self._media_position);self.player.durationChanged.connect(self._media_duration)
        self.preview_timer=QTimer(self);self.preview_timer.setTimerType(Qt.PreciseTimer);self.preview_timer.setInterval(8);self.preview_timer.timeout.connect(self._tick);self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(90);self.debounce.timeout.connect(self.render_preview)
        root=QWidget();layout=QVBoxLayout(root);layout.addWidget(self._step_navigator());body=QHBoxLayout();layout.addLayout(body,1);body.addWidget(self._left_panel(),2);body.addWidget(self._center_panel(),5);body.addWidget(self._right_panel(),3);layout.addWidget(self._bottom_panel());self.setCentralWidget(root);self._apply_theme();self.refresh_templates();self.sync_controls();self.app_settings=AppSettings();self._restore_settings();self._localize_existing();QTimer.singleShot(200,self._first_run_and_resume)
    def _left_panel(self):
        tabs=QTabWidget();media=QWidget();m=QVBoxLayout(media);self.audio_list=QListWidget();m.addWidget(QLabel("Audio Files"));m.addWidget(self.audio_list);button=QPushButton("Add Audio");button.clicked.connect(self.add_audio);m.addWidget(button);tabs.addTab(media,"Media")
        ref=QWidget();r=QVBoxLayout(ref);self.ref_list=QListWidget();r.addWidget(QLabel("Reference Images (max 5)"));r.addWidget(self.ref_list);row=QHBoxLayout()
        for text,fn in (("Add Image",self.add_reference),("Remove",self.remove_reference),("Clear",self.clear_reference)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        r.addLayout(row);b=QPushButton("Auto Analyze Images");b.clicked.connect(self.analyze_reference_images);r.addWidget(b);roirow=QHBoxLayout();b=QPushButton("Draw ROI");b.clicked.connect(self.draw_roi);roirow.addWidget(b);b=QPushButton("Coordinate ROI");b.clicked.connect(self.set_roi);roirow.addWidget(b);b=QPushButton("Reset ROI");b.clicked.connect(self.reset_roi);roirow.addWidget(b);r.addLayout(roirow);self.video_label=QLabel("No reference video");r.addWidget(self.video_label);b=QPushButton("Select 5–10s Video");b.clicked.connect(self.add_video);r.addWidget(b);b=QPushButton("Analyze Motion");b.clicked.connect(self.analyze_motion);r.addWidget(b);tabs.addTab(ref,"Reference")
        templates=QWidget();t=QVBoxLayout(templates);self.template_list=QListWidget();self.template_list.itemClicked.connect(self.apply_gallery);t.addWidget(self.template_list);b=QPushButton("Save as My Template");b.clicked.connect(self.save_my_template);t.addWidget(b);tabs.addTab(templates,"파형 스타일");self.playlist_panel=PlaylistPanel();tabs.addTab(self.playlist_panel,"곡 목록");self.queue_panel=QueuePanel(self.queue_manager);self.queue_panel.startRequested.connect(self.start_queue);tabs.addTab(self.queue_panel,"예약 작업");self.left_tabs=tabs;return tabs
    def _center_panel(self):
        box=QWidget();v=QVBoxLayout(box);self.preview=QLabel("Add audio and click Analyze");self.preview.setMinimumSize(640,360);self.preview.setAlignment(Qt.AlignCenter);self.preview.setStyleSheet("background:#080B10;border:1px solid #283343");v.addWidget(self.preview,1);row=QHBoxLayout()
        for text,fn in (("▶ Play",self.play),("Ⅱ Pause",self.pause),("■ Stop",self.stop)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.timeline=QSlider(Qt.Horizontal);self.timeline.setRange(0,0);self.timeline.sliderMoved.connect(self.seek);row.addWidget(self.timeline,1);self.time_label=QLabel("00:00 / 00:00");row.addWidget(self.time_label);v.addLayout(row);return box
    def _right_panel(self):
        self.tabs=QTabWidget();self.fields={};self.combos={};self.checks={};self.simple_controls=SimpleControls();self.simple_controls.changed.connect(self.simple_changed);self.tabs.addTab(self.simple_controls,"간편 설정");
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
        widget=QWidget();form=QFormLayout(widget);self.export_format=QComboBox();self.export_format.addItems(["mp4","webm","mov"]);self.resolution=QComboBox();self.resolution.addItems(["1920x1080","1080x1920","1080x1080","Custom"]);self.export_fps=QComboBox();self.export_fps.addItems(["24","30","60"]);self.renderer_choice=QComboBox();self.renderer_choice.addItems(["AUTO","GPU","CPU"]);self.quality=QComboBox();self.quality.addItems(["BALANCED","QUALITY","PREVIEW"]);self.skip_completed=QCheckBox();self.skip_completed.setChecked(True);self.custom_width=QSpinBox();self.custom_width.setRange(320,7680);self.custom_width.setValue(1920);self.custom_height=QSpinBox();self.custom_height.setRange(320,7680);self.custom_height.setValue(1080);self.ffmpeg_path=QLineEdit();self.ffmpeg_path.setPlaceholderText("System PATH (default)")
        for label,control in (("Format",self.export_format),("Resolution",self.resolution),("Custom Width",self.custom_width),("Custom Height",self.custom_height),("FPS",self.export_fps),("Renderer",self.renderer_choice),("Quality",self.quality),("FFmpeg Path",self.ffmpeg_path),("Skip completed outputs",self.skip_completed)):form.addRow(label,control)
        self.format_help=QLabel("MP4 H.264 · black background · CapCut Screen blend");self.export_format.currentTextChanged.connect(self._format_help);form.addRow(self.format_help);return widget
    def _bottom_panel(self):
        box=QWidget();v=QVBoxLayout(box);row=QHBoxLayout()
        for text,fn in (("음원 분석",self.analyze_audio),("지금 만들기",self.render),("대기열에 추가",self.add_to_queue),("예약 작업 모두 시작",self.start_queue),("음원 검사",self.validate_tracks),("환경 검사",self.system_check),("작업 중지",self.cancel)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        v.addLayout(row);self.song_progress=QProgressBar();self.total_progress=QProgressBar();v.addWidget(self.song_progress);v.addWidget(self.total_progress);self.status=QLabel("Ready");self.performance=QLabel("Renderer: —  |  Preview FPS: —  |  Cache: —  |  Analysis: —");v.addWidget(self.status);v.addWidget(self.performance);return box
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
        QMessageBox.information(self,"예약 작업 완료",f"모든 예약 작업이 끝났습니다.\n성공 세트: {result.sets_success}\n실패 세트: {result.sets_failed}\n총 작업시간: {result.elapsed/60:.1f}분")
        action=self.completion_action.currentText()
        if action.startswith("완료 후 프로그램"):self.close()
        elif action.startswith("완료 후 PC") and QMessageBox.question(self,"PC 종료","60초 후 PC를 종료할까요?",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:subprocess.Popen(["shutdown","/s","/t","60"])
    def _step_navigator(self):
        widget=QWidget();layout=QHBoxLayout(widget);self.step_labels=[]
        for key in ("step1","step2","step3","step4","step5"):
            label=QLabel(self.translator.tr(key));label.setAlignment(Qt.AlignCenter);label.setMinimumHeight(38);label.setStyleSheet("background:#222B37;color:#B7C0CB;border:1px solid #394657;border-radius:5px;padding:5px")
            layout.addWidget(label);self.step_labels.append(label)
        self.step_labels[0].setStyleSheet("background:#4A90E2;color:#FFFFFF;border:1px solid #4A90E2;border-radius:5px;padding:5px")
        return widget
    def _localize_existing(self):
        pairs={"Media":"음원","Audio Files":"음원","Audio":"음악 반응","Reference":"참고 파형","Design":"디자인","Queue":"예약 작업","Playlist":"곡 목록","Templates":"파형 스타일","Effects":"효과","Export":"저장 설정","Add Audio":"음원 추가","Add Image":"이미지 추가","Remove":"삭제","Clear":"전체 지우기","Auto Analyze Images":"참고 이미지 분석","Draw ROI":"ROI 선택","Coordinate ROI":"ROI 좌표 입력","Reset ROI":"ROI 초기화","Analyze Motion":"움직임 분석","Save as My Template":"내 스타일로 저장","Play":"재생","Pause":"일시정지","Stop":"정지","Format":"출력 형식","Resolution":"해상도","FPS":"프레임 속도","Renderer":"렌더 방식","Quality":"품질","Ready":"준비됨"}
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
        for index in range(1,min(4,self.tabs.count())):self.tabs.setTabVisible(index,visible)
        self.simple_controls.advanced.setText("간편 설정으로 돌아가기" if visible else self.translator.tr("advanced"))
    def simple_changed(self,values):
        self.template["height"]={"작게":.14,"보통":.22,"크게":.34}.get(values.get("movement"),self.template.get("height",.22))
        self.template["response"]={"느리게":.8,"자연스럽게":1.25,"빠르게":1.9}.get(values.get("response"),1.25)
        self.template["smoothing"]={"잔잔하게":.55,"기본":.15,"선명하게":.02}.get(values.get("smooth"),.15)
        self.template["glow"] = values.get("glow")!="없음";self.template["glow_strength"]={"없음":0,"약하게":.25,"보통":.55,"강하게":.9}.get(values.get("glow"),.55)
        self.template["bass_weight"]={"약하게":.6,"기본":1.0,"강하게":1.5}.get(values.get("bass"),1.0);self.template["high_weight"]={"약하게":.6,"기본":1.0,"강하게":1.5}.get(values.get("treble"),1.0)
        self.sync_controls();self.debounce.start()
    def add_to_queue(self):
        if not self.audio_files:return
        out=QFileDialog.getExistingDirectory(self,"출력 폴더 선택","output")
        if not out:return
        export={"format":self.export_format.currentText(),"resolution":self.resolution.currentText(),"fps":int(self.export_fps.currentText()),"quality":self.quality.currentText(),"renderer":self.renderer_choice.currentText(),"ffmpeg_path":self.ffmpeg_path.text() or None}
        name=f"{datetime.date.today().isoformat()}_{self.template.get('name','파형 스타일')}"
        job=JobSet(name=name,tracks=[{"audio":path,"preset":self.template.get("name","01_clean_bars"),"format":export["format"]} for path in self.audio_files],preset=self.template.get("name","01_clean_bars"),export=export,output_dir=out)
        try:self.queue_manager.add(job);self.queue_panel.refresh();self.left_tabs.setCurrentWidget(self.queue_panel);self.status.setText(f"예약 작업에 추가됨: {len(self.queue_manager.sets)} / 5")
        except ValueError as exc:QMessageBox.warning(self,"예약 작업",str(exc))
    def start_queue(self):
        if not self.queue_manager.sets:return
        checks=self.queue_manager.preflight(check_template=resolve_template);bad=[item for item in checks if not item["ready"]]
        if bad:
            QMessageBox.warning(self,"실행 전 검사","일부 예약 작업을 시작할 수 없습니다. 예약 작업 탭에서 실행 전 검사 결과를 확인하세요.")
            return
        self.start_task("queue",(self.queue_manager,self.prevent_sleep.isChecked()));self.status.setText("예약 작업을 시작했습니다")
    def _apply_theme(self):self.setStyleSheet("QWidget{background:#11151C;color:#F4F7FA;font-size:13px}QGroupBox{border:1px solid #394657;border-radius:5px;margin-top:8px;padding-top:10px}QGroupBox::title{color:#F4F7FA}QPushButton,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit{background:#222B37;color:#F4F7FA;border:1px solid #394657;padding:7px;border-radius:4px;min-height:24px}QPushButton:hover,QComboBox:hover{background:#2E4663;border-color:#4A90E2}QPushButton:pressed,QPushButton:checked{background:#4A90E2;color:white}QTabWidget::pane{background:#181E27;border:1px solid #394657}QTabBar::tab{background:#181E27;color:#B7C0CB;padding:10px 14px;min-height:20px}QTabBar::tab:selected{background:#4A90E2;color:#FFFFFF}QTabBar::tab:hover{background:#2E4663;color:#FFFFFF}QListWidget,QTableWidget{background:#181E27;color:#F4F7FA;border:1px solid #394657}QHeaderView::section{background:#222B37;color:#F4F7FA;padding:6px}QSlider::groove:horizontal{background:#394657;height:6px}QSlider::handle:horizontal{background:#4A90E2;width:14px;margin:-5px 0}QProgressBar{background:#222B37;color:#F4F7FA;border:1px solid #394657;text-align:center;min-height:20px}QProgressBar::chunk{background:#4A90E2}QToolTip{background:#222B37;color:#F4F7FA;border:1px solid #4A90E2}")
    def add_audio(self):
        files,_=QFileDialog.getOpenFileNames(self,"Audio files","","Audio (*.wav *.mp3 *.flac *.m4a *.ogg)");self.audio_files.extend(x for x in files if x not in self.audio_files);self.audio_list.clear();self.audio_list.addItems(self.audio_files)
        if self.audio_files:self.player.setSource(QUrl.fromLocalFile(self.audio_files[0]))
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
        path,_=QFileDialog.getOpenFileName(self,"Reference video","","Video (*.mp4 *.mov *.webm *.mkv)");self.reference_video=path or None;self.video_label.setText(Path(path).name if path else "No reference video")
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
        if self.reference_images:self.start_task("images",(self.reference_images,self.roi))
    def analyze_motion(self):
        if self.reference_video:self.start_task("video",(self.reference_video,self.roi,10))
    def apply_reference(self,result):
        summary="\n".join(f"{key}: {value}" for key,value in list(result.items())[:12])
        message=f"Analysis result:\n{summary}\n\nApply to current template?"
        if QMessageBox.question(self,"Reference analysis",message)!=QMessageBox.Yes:return
        before=copy.deepcopy(self.template);self.template.update(result);self.sync_controls();self.debounce.start();changed=[f"{key}: {before.get(key)} -> {self.template.get(key)}" for key in result if before.get(key)!=self.template.get(key)];QMessageBox.information(self,"Reference applied","Applied to current template:\n"+"\n".join(changed[:12]))
    def refresh_templates(self):
        self.template_list.clear()
        values=np.abs(np.sin(np.linspace(0,np.pi*3,36)))*.8+.1
        for path,data in list_templates(resource_path("templates"),"my_templates"):
            item=QListWidgetItem(data["name"]);item.setData(Qt.UserRole,str(path));thumb_path,_=get_thumbnail(dict(data,glow=False));item.setIcon(QIcon(str(thumb_path)));self.template_list.addItem(item)
    def apply_gallery(self,item):self.template=load_template(item.data(Qt.UserRole));self.sync_controls();self.debounce.start()
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
        self.thread=QThread();self.worker=TaskWorker(kind,payload);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.status.connect(self.status.setText);self.worker.progress.connect(lambda a,b:self.total_progress.setValue(int(a*100/b)));self.worker.failed.connect(self.task_failed);self.worker.done.connect(lambda result:self.task_done(kind,result));self.worker.done.connect(self.thread.quit);self.worker.failed.connect(self.thread.quit);self.thread.start();self.status.setText(f"{kind.title()} running…")
    def task_done(self,kind,result):
        if kind=="analysis":
            features,hit,elapsed=result;self.preview_engine.features=features;self.preview_engine.template=dict(self.template);self.preview_engine.metrics.cache_hit=hit;self.preview_engine.metrics.analysis_seconds=elapsed;self.timeline.setMaximum(int(float(features["duration"][0])*1000));self.start_preview_worker(features);self.render_preview()
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
    def _format_help(self,value):self.format_help.setText({"mp4":"MP4 H.264 · black background · CapCut Screen blend","webm":"WebM VP9 · transparent alpha","mov":"MOV ProRes 4444 · transparent alpha"}[value])
    def render(self):
        if not self.audio_files:return
        out=QFileDialog.getExistingDirectory(self,"Output directory","output")
        if not out:return
        if self.resolution.currentText()=="Custom":w,h=self.custom_width.value(),self.custom_height.value()
        else:w,h=map(int,self.resolution.currentText().split("x"))
        space=disk_warning(out);
        if space["warning"] and QMessageBox.warning(self,"Low Disk Space",f"Only {space['free']/1024**3:.1f} GB is available. Continue?",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        options=ExportOptions(w,h,int(self.export_fps.currentText()),self.quality.currentText(),self.renderer_choice.currentText(),self.export_format.currentText(),self.ffmpeg_path.text() or None);self.start_task("render",(self.audio_files,out,copy.deepcopy(self.template),options,self.skip_completed.isChecked()))
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
        self.ffmpeg_path.setText(str(self.app_settings.get("ffmpeg_path","") or ""));self.app_settings.restore_window(self)
    def closeEvent(self,event):
        self.app_settings.set("renderer_mode",self.renderer_choice.currentText());self.app_settings.set("quality",self.quality.currentText());self.app_settings.set("resolution",self.resolution.currentText());self.app_settings.set("fps",self.export_fps.currentText());self.app_settings.set("ffmpeg_path",self.ffmpeg_path.text());self.app_settings.save_window(self);self.stop_preview_worker();super().closeEvent(event)
    def system_check(self):
        report=format_report(check_system());QMessageBox.information(self,"System Check",report)
    def cancel(self):
        if self.worker:self.worker.cancel();self.status.setText("Cancelling…")
