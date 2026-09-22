from __future__ import annotations
import sys, time
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication,QComboBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QListWidget,QMainWindow,QProgressBar,QPushButton,QSlider,QVBoxLayout,QWidget
from audio.analyzer import AnalysisSettings, analyze_file
from animation.engine import AnimationEngine
from pipeline.batch import BatchRunner
from pipeline.exporter import ExportOptions, render_audio
from render.renderer import RendererFactory
from template_system import load_template

class Worker(QObject):
    progress=Signal(int,int); status=Signal(str); done=Signal(object); failed=Signal(str)
    def __init__(self,mode,files,template,renderer="AUTO",quality="BALANCED"): super().__init__(); self.mode=mode; self.files=files; self.template=template; self.renderer=renderer; self.quality=quality; self.cancelled=False; self.runner=None
    @Slot()
    def run(self):
        try:
            if self.mode=="analyze": result=analyze_file(self.files[0],AnalysisSettings(bands=int(self.template["bands"])),logger=self.status.emit)[0]
            else:
                self.runner=BatchRunner(); result=self.runner.run(self.files,"output",self.template,ExportOptions(renderer=self.renderer,quality=self.quality),progress=lambda a,b,e:(self.progress.emit(a,b),self.status.emit(f"ETA {e:.0f}s")))
            self.done.emit(result)
        except Exception as exc: self.failed.emit(str(exc))
    def cancel(self):
        self.cancelled=True
        if self.runner: self.runner.cancel()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Music Wave Studio 0.5"); self.resize(1200,760); self.audio=[]; self.template=load_template("templates/chill_glow.json"); self.thread=None; self.worker=None
        root=QWidget(); outer=QVBoxLayout(root); columns=QHBoxLayout(); outer.addLayout(columns,1)
        left=QVBoxLayout(); self.audio_list=QListWidget(); add=QPushButton("Add Audio Files"); add.clicked.connect(self.add_audio); left.addWidget(QLabel("Audio Files")); left.addWidget(self.audio_list); left.addWidget(add); left.addWidget(QLabel("Reference Images / Video")); left.addWidget(QPushButton("Add Reference")); left.addWidget(QLabel("Templates")); left.addWidget(QLabel(self.template["name"])); columns.addLayout(left,1)
        center=QVBoxLayout(); self.preview=QLabel("Waveform / Template Preview"); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumSize(520,300); self.preview.setStyleSheet("background:#111;color:#aaa"); center.addWidget(self.preview); columns.addLayout(center,3)
        form=QFormLayout(); self.controls={}
        for name,lo,hi,value in (("Bands",8,256,int(self.template["bands"])),("Response",10,300,int(self.template["response"]*100)),("Attack",0,100,int(self.template["attack"]*100)),("Decay",0,100,int(self.template["decay"]*100)),("Smoothing",0,95,int(self.template["smoothing"]*100)),("Bass",0,200,100),("Mid",0,200,100),("High",0,200,100),("Width",10,100,int(self.template["width"]*100)),("Height",5,90,int(self.template["height"]*100)),("Bar Width",5,100,int(self.template["bar_width"]*100))):
            slider=QSlider(Qt.Horizontal); slider.setRange(lo,hi); slider.setValue(value); slider.valueChanged.connect(self.apply_controls); self.controls[name]=slider; form.addRow(name,slider)
        self.renderer=QComboBox(); self.renderer.addItems(["AUTO","GPU","CPU"]); self.quality=QComboBox(); self.quality.addItems(["PREVIEW","BALANCED","QUALITY"]); form.addRow("Color / Gradient / Glow / Mirror",QLabel("Template JSON")); form.addRow("Position",QLabel(self.template["position"])); form.addRow("Renderer",self.renderer); form.addRow("Quality",self.quality); columns.addLayout(form,2)
        actions=QHBoxLayout();
        for label,fn in (("Analyze",self.analyze),("Preview",self.show_preview),("Render",self.render),("Batch Render",self.render),("Cancel",self.cancel)):
            button=QPushButton(label); button.clicked.connect(fn); actions.addWidget(button)
        outer.addLayout(actions); self.song_progress=QProgressBar(); self.total_progress=QProgressBar(); outer.addWidget(self.song_progress); outer.addWidget(self.total_progress); self.message=QLabel("Ready"); outer.addWidget(self.message); self.setCentralWidget(root)
    def add_audio(self):
        files,_=QFileDialog.getOpenFileNames(self,"Audio files","","Audio (*.wav *.mp3 *.flac *.m4a *.ogg)"); self.audio.extend(files); self.audio_list.addItems(files)
    def apply_controls(self):
        mapping={"Bands":("bands",1),"Response":("response",.01),"Attack":("attack",.01),"Decay":("decay",.01),"Smoothing":("smoothing",.01),"Bass":("bass_weight",.01),"Mid":("mid_weight",.01),"High":("high_weight",.01),"Width":("width",.01),"Height":("height",.01),"Bar Width":("bar_width",.01)}
        for label,(key,scale) in mapping.items(): self.template[key]=self.controls[label].value()*scale
    def start(self,mode):
        if not self.audio: self.message.setText("Add an audio file first"); return
        self.thread=QThread(); self.worker=Worker(mode,self.audio,self.template,self.renderer.currentText(),self.quality.currentText()); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.status.connect(self.message.setText); self.worker.progress.connect(lambda a,b:self.total_progress.setValue(int(a*100/b))); self.worker.done.connect(self.finished); self.worker.failed.connect(self.failed); self.worker.done.connect(self.thread.quit); self.worker.failed.connect(self.thread.quit); self.thread.start()
    def analyze(self): self.start("analyze")
    def render(self): self.start("render")
    def show_preview(self):
        if not self.audio: return
        try:
            features,_=analyze_file(self.audio[0],AnalysisSettings(fps=24,bands=int(self.template["bands"]))); image=RendererFactory.create(self.renderer.currentText()).render_rgba(640,360,AnimationEngine(features,self.template).sample(min(5,float(features["duration"][0])/2)),self.template); q=QImage(image.data,640,360,image.strides[0],QImage.Format_RGBA8888).copy(); self.preview.setPixmap(QPixmap.fromImage(q))
        except Exception as exc: self.message.setText(str(exc))
    def finished(self,result): self.message.setText("Completed"); self.total_progress.setValue(100)
    def failed(self,error): self.message.setText(f"Failed: {error}")
    def cancel(self):
        if self.worker: self.worker.cancel(); self.message.setText("Cancelling...")

def main():
    application=QApplication(sys.argv); window=MainWindow(); window.show(); return application.exec()
if __name__=="__main__": raise SystemExit(main())
