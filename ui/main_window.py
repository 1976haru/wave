from __future__ import annotations
import copy,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QObject,QMetaObject,QThread,QTimer,QUrl,Signal,Slot,Qt
from PySide6.QtGui import QColor,QIcon,QImage,QPixmap
from PySide6.QtMultimedia import QAudioOutput,QMediaPlayer
from PySide6.QtWidgets import (QApplication,QCheckBox,QColorDialog,QComboBox,QFileDialog,QFormLayout,QGroupBox,QHBoxLayout,QInputDialog,QLabel,QListWidget,QListWidgetItem,QMainWindow,QMessageBox,QProgressBar,QPushButton,QScrollArea,QSlider,QSpinBox,QDoubleSpinBox,QTabWidget,QVBoxLayout,QWidget)
from audio.analyzer import AnalysisSettings,analyze_file
from core.paths import resource_path
from animation.engine import AnimationEngine
from pipeline.batch import BatchRunner
from pipeline.exporter import ExportOptions,output_extension
from preview.engine import PreviewEngine,format_time
from preview.scheduler import FrameScheduler
from preview.worker import LatestFrameMailbox,PreviewRenderWorker
from reference.analyzer import analyze_images,analyze_video
from render.renderer import CPURenderer,RendererFactory
from template_system import list_templates,load_template,save_template
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
                started=time.perf_counter(); features,hit=analyze_file(self.payload[0],AnalysisSettings(fps=24,bands=self.payload[1]),logger=self.status.emit); result=(features,hit,time.perf_counter()-started)
            elif self.kind=="render":
                files,out,template,options,skip_completed=self.payload;self.runner=BatchRunner();result=self.runner.run(files,out,template,options,skip_completed=skip_completed,progress=lambda a,b,e:(self.progress.emit(a,b),self.status.emit(f"ETA {e:.0f}s")))
            elif self.kind=="images":result=analyze_images(*self.payload)
            elif self.kind=="video":result=analyze_video(*self.payload)
            elif self.kind=="validation":result=validate_audio_folder(*self.payload)
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
        super().__init__();self.setWindowTitle("Music Wave Studio v0.6");self.resize(1500,900);self.audio_files=[];self.reference_images=[];self.reference_video=None;self.roi=None;self.template=load_template(resource_path("templates/01_clean_bars.json"));self.preview_engine=PreviewEngine();self.scheduler=FrameScheduler(24);self.current_time=0;self.thread=None;self.worker=None;self.preview_thread=None;self.preview_worker=None;self.preview_mailbox=None;self._syncing=False
        self.player=QMediaPlayer();self.audio_output=QAudioOutput();self.player.setAudioOutput(self.audio_output);self.player.positionChanged.connect(self._media_position);self.player.durationChanged.connect(self._media_duration)
        self.preview_timer=QTimer(self);self.preview_timer.setTimerType(Qt.PreciseTimer);self.preview_timer.setInterval(8);self.preview_timer.timeout.connect(self._tick);self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(90);self.debounce.timeout.connect(self.render_preview)
        root=QWidget();layout=QVBoxLayout(root);body=QHBoxLayout();layout.addLayout(body,1);body.addWidget(self._left_panel(),2);body.addWidget(self._center_panel(),5);body.addWidget(self._right_panel(),3);layout.addWidget(self._bottom_panel());self.setCentralWidget(root);self._apply_theme();self.refresh_templates();self.sync_controls()
    def _left_panel(self):
        tabs=QTabWidget();media=QWidget();m=QVBoxLayout(media);self.audio_list=QListWidget();m.addWidget(QLabel("Audio Files"));m.addWidget(self.audio_list);button=QPushButton("Add Audio");button.clicked.connect(self.add_audio);m.addWidget(button);tabs.addTab(media,"Media")
        ref=QWidget();r=QVBoxLayout(ref);self.ref_list=QListWidget();r.addWidget(QLabel("Reference Images (max 5)"));r.addWidget(self.ref_list);row=QHBoxLayout()
        for text,fn in (("Add Image",self.add_reference),("Remove",self.remove_reference),("Clear",self.clear_reference)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        r.addLayout(row);b=QPushButton("Auto Analyze Images");b.clicked.connect(self.analyze_reference_images);r.addWidget(b);roirow=QHBoxLayout();b=QPushButton("Draw ROI");b.clicked.connect(self.draw_roi);roirow.addWidget(b);b=QPushButton("Coordinate ROI");b.clicked.connect(self.set_roi);roirow.addWidget(b);b=QPushButton("Reset ROI");b.clicked.connect(self.reset_roi);roirow.addWidget(b);r.addLayout(roirow);self.video_label=QLabel("No reference video");r.addWidget(self.video_label);b=QPushButton("Select 5–10s Video");b.clicked.connect(self.add_video);r.addWidget(b);b=QPushButton("Analyze Motion");b.clicked.connect(self.analyze_motion);r.addWidget(b);tabs.addTab(ref,"Reference")
        templates=QWidget();t=QVBoxLayout(templates);self.template_list=QListWidget();self.template_list.itemClicked.connect(self.apply_gallery);t.addWidget(self.template_list);b=QPushButton("Save as My Template");b.clicked.connect(self.save_my_template);t.addWidget(b);tabs.addTab(templates,"Templates");return tabs
    def _center_panel(self):
        box=QWidget();v=QVBoxLayout(box);self.preview=QLabel("Add audio and click Analyze");self.preview.setMinimumSize(640,360);self.preview.setAlignment(Qt.AlignCenter);self.preview.setStyleSheet("background:#080B10;border:1px solid #283343");v.addWidget(self.preview,1);row=QHBoxLayout()
        for text,fn in (("▶ Play",self.play),("Ⅱ Pause",self.pause),("■ Stop",self.stop)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.timeline=QSlider(Qt.Horizontal);self.timeline.setRange(0,0);self.timeline.sliderMoved.connect(self.seek);row.addWidget(self.timeline,1);self.time_label=QLabel("00:00 / 00:00");row.addWidget(self.time_label);v.addLayout(row);return box
    def _right_panel(self):
        self.tabs=QTabWidget();self.fields={};self.combos={};self.checks={};
        audio=("Bands",8,256,1),("Response",.1,3,.01),("Attack",0,1,.01),("Decay",0,1,.01),("Smoothing",0,.95,.01),("Onset Boost",0,2,.01),("Bass Weight",0,2,.01),("Mid Weight",0,2,.01),("High Weight",0,2,.01)
        design=("Width",.1,1,.01),("Height",.05,.9,.01),("Bar Width",.05,1,.01),("Gap",0,.95,.01),("Roundness",0,1,.01),("Opacity",0,1,.01)
        self.tabs.addTab(self._control_tab(audio,"audio"),"Audio");widget=self._control_tab(design,"design");form=widget.layout();self._combo(form,"Style",["bars","line","dot"],"renderer");self._combo(form,"Position",["top","center","bottom"],"position");self._check(form,"Mirror","mirror");self._color_button(form,"Main Color","color");self._check(form,"Gradient","gradient");self._color_button(form,"Gradient Start","gradient_start");self._color_button(form,"Gradient End","gradient_end");self.tabs.addTab(widget,"Design")
        effects=QWidget();f=QFormLayout(effects);self._check(f,"Glow","glow");self._number(f,"Glow Strength",0,2,.05,"glow_strength");self._number(f,"Glow Radius",0,40,1,"glow_radius");self._check(f,"Shadow","shadow");self.tabs.addTab(effects,"Effects");self.tabs.addTab(self._export_tab(),"Export");scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.tabs);return scroll
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
        widget=QWidget();form=QFormLayout(widget);self.export_format=QComboBox();self.export_format.addItems(["mp4","webm","mov"]);self.resolution=QComboBox();self.resolution.addItems(["1920x1080","1080x1920","1080x1080","Custom"]);self.export_fps=QComboBox();self.export_fps.addItems(["24","30","60"]);self.renderer_choice=QComboBox();self.renderer_choice.addItems(["AUTO","GPU","CPU"]);self.quality=QComboBox();self.quality.addItems(["BALANCED","QUALITY","PREVIEW"]);self.skip_completed=QCheckBox();self.skip_completed.setChecked(True);self.custom_width=QSpinBox();self.custom_width.setRange(320,7680);self.custom_width.setValue(1920);self.custom_height=QSpinBox();self.custom_height.setRange(320,7680);self.custom_height.setValue(1080)
        for label,control in (("Format",self.export_format),("Resolution",self.resolution),("Custom Width",self.custom_width),("Custom Height",self.custom_height),("FPS",self.export_fps),("Renderer",self.renderer_choice),("Quality",self.quality),("Skip completed outputs",self.skip_completed)):form.addRow(label,control)
        self.format_help=QLabel("MP4 H.264 · black background · CapCut Screen blend");self.export_format.currentTextChanged.connect(self._format_help);form.addRow(self.format_help);return widget
    def _bottom_panel(self):
        box=QWidget();v=QVBoxLayout(box);row=QHBoxLayout()
        for text,fn in (("Analyze",self.analyze_audio),("Render",self.render),("Batch Render",self.render),("Validate 15 Tracks",self.validate_tracks),("System Check",self.system_check),("Cancel",self.cancel)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        v.addLayout(row);self.song_progress=QProgressBar();self.total_progress=QProgressBar();v.addWidget(self.song_progress);v.addWidget(self.total_progress);self.status=QLabel("Ready");self.performance=QLabel("Renderer: —  |  Preview FPS: —  |  Cache: —  |  Analysis: —");v.addWidget(self.status);v.addWidget(self.performance);return box
    def _apply_theme(self):self.setStyleSheet("QWidget{background:#121720;color:#DDE6F1;font-size:12px}QPushButton,QComboBox,QSpinBox,QDoubleSpinBox{background:#202938;border:1px solid #344258;padding:6px;border-radius:4px}QPushButton:hover{border-color:#55B8FF}QTabWidget::pane{border:1px solid #283343}QListWidget{background:#0D1219;border:1px solid #283343}QProgressBar{border:1px solid #344258;text-align:center}QProgressBar::chunk{background:#3B9EFF}")
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
            item=QListWidgetItem(data["name"]);item.setData(Qt.UserRole,str(path));thumb=CPURenderer().render_rgba(180,72,{"values":values},dict(data,glow=False));image=QImage(thumb.data,180,72,thumb.strides[0],QImage.Format_RGBA8888).copy();item.setIcon(QIcon(QPixmap.fromImage(image)));self.template_list.addItem(item)
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
        if self.audio_files:self.start_task("analysis",(self.audio_files[0],int(self.template["bands"])))
    def start_task(self,kind,payload):
        if self.thread and self.thread.isRunning():return
        self.thread=QThread();self.worker=TaskWorker(kind,payload);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.status.connect(self.status.setText);self.worker.progress.connect(lambda a,b:self.total_progress.setValue(int(a*100/b)));self.worker.failed.connect(self.task_failed);self.worker.done.connect(lambda result:self.task_done(kind,result));self.worker.done.connect(self.thread.quit);self.worker.failed.connect(self.thread.quit);self.thread.start();self.status.setText(f"{kind.title()} running…")
    def task_done(self,kind,result):
        if kind=="analysis":
            features,hit,elapsed=result;self.preview_engine.features=features;self.preview_engine.template=dict(self.template);self.preview_engine.metrics.cache_hit=hit;self.preview_engine.metrics.analysis_seconds=elapsed;self.timeline.setMaximum(int(float(features["duration"][0])*1000));self.start_preview_worker(features);self.render_preview()
        elif kind in ("images","video"):self.apply_reference(result)
        elif kind=="validation":self.status.setText(f"Validation: {result['successful_tracks']}/{result['total_tracks']} ready; report saved");return
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
        options=ExportOptions(w,h,int(self.export_fps.currentText()),self.quality.currentText(),self.renderer_choice.currentText(),self.export_format.currentText());self.start_task("render",(self.audio_files,out,copy.deepcopy(self.template),options,self.skip_completed.isChecked()))
    def validate_tracks(self):
        folder=QFileDialog.getExistingDirectory(self,"Select folder with up to 15 tracks")
        if folder:self.start_task("validation",(folder,"validation_results/user_audio_validation.json",15))
    def closeEvent(self,event):
        self.stop_preview_worker();super().closeEvent(event)
    def system_check(self):
        report=format_report(check_system());QMessageBox.information(self,"System Check",report)
    def cancel(self):
        if self.worker:self.worker.cancel();self.status.setText("Cancelling…")
