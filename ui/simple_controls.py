from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox,QFormLayout,QPushButton,QVBoxLayout,QWidget
class SimpleControls(QWidget):
    changed=Signal(dict)
    def __init__(self,parent=None):
        super().__init__(parent);self.controls={};layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        options={"movement":["작게","보통","크게"],"response":["느리게","자연스럽게","빠르게"],"smooth":["잔잔하게","기본","선명하게"],"glow":["없음","약하게","보통","강하게"],"bass":["약하게","기본","강하게"],"treble":["약하게","기본","강하게"]}
        labels={"movement":"움직임 크기","response":"반응 속도","smooth":"움직임 부드러움","glow":"빛 번짐","bass":"저음 반응","treble":"고음 반응"}
        for key,items in options.items():
            combo=QComboBox();combo.addItems(items);combo.currentTextChanged.connect(lambda _text,k=key:self._emit(k));self.controls[key]=combo;form.addRow(labels[key],combo)
        self.advanced=QPushButton("고급 설정 펼치기");self.advanced.setCheckable(True);layout.addWidget(self.advanced)
    def _emit(self,key):
        self.changed.emit({name:control.currentText() for name,control in self.controls.items()})
    def set_values(self,values):
        for key,value in values.items():
            if key in self.controls:self.controls[key].setCurrentText(value)
