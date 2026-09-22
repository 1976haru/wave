from __future__ import annotations
from dataclasses import dataclass
from PySide6.QtCore import QPoint,QRect,Qt,Signal
from PySide6.QtGui import QColor,QImage,QMouseEvent,QPainter,QPen,QPixmap
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QLabel,QPushButton,QVBoxLayout

@dataclass(frozen=True)
class ImageTransform:
    widget_width:int;widget_height:int;image_width:int;image_height:int
    @property
    def content_rect(self):
        scale=min(self.widget_width/self.image_width,self.widget_height/self.image_height);w=self.image_width*scale;h=self.image_height*scale;return ((self.widget_width-w)/2,(self.widget_height-h)/2,w,h)
    def widget_to_image(self,x,y):
        left,top,width,height=self.content_rect;ix=round((min(max(x,left),left+width)-left)*self.image_width/width);iy=round((min(max(y,top),top+height)-top)*self.image_height/height);return min(ix,self.image_width),min(iy,self.image_height)
    def image_to_widget(self,x,y):
        left,top,width,height=self.content_rect;return left+x*width/self.image_width,top+y*height/self.image_height
    def rect_to_image(self,rect):
        x1,y1=self.widget_to_image(rect.left(),rect.top());x2,y2=self.widget_to_image(rect.right()+1,rect.bottom()+1);return min(x1,x2),min(y1,y2),abs(x2-x1),abs(y2-y1)

class ROISelectionModel:
    def __init__(self):self.anchor=None;self.current=None;self.active=False
    def press(self,x,y):self.anchor=(x,y);self.current=(x,y);self.active=True
    def move(self,x,y):
        if self.active:self.current=(x,y)
    def release(self,x,y):self.move(x,y);self.active=False
    def reset(self):self.anchor=self.current=None;self.active=False
    @property
    def rectangle(self):
        if self.anchor is None or self.current is None:return None
        x1,y1=self.anchor;x2,y2=self.current;return QRect(QPoint(min(x1,x2),min(y1,y2)),QPoint(max(x1,x2),max(y1,y2))).normalized()

class ROIImageLabel(QLabel):
    roiChanged=Signal(object)
    def __init__(self,image_path,parent=None):
        super().__init__(parent);self.setMinimumSize(720,450);self.setAlignment(Qt.AlignCenter);self.setMouseTracking(True);self.model=ROISelectionModel();self.original=QImage(str(image_path))
        if self.original.isNull():raise ValueError(f"Cannot read reference image: {image_path}")
    @property
    def transform(self):return ImageTransform(max(1,self.width()),max(1,self.height()),self.original.width(),self.original.height())
    def selected_roi(self):
        rect=self.model.rectangle
        if rect is None:return None
        roi=self.transform.rect_to_image(rect);return roi if roi[2]>=2 and roi[3]>=2 else None
    def reset_roi(self):self.model.reset();self.update();self.roiChanged.emit(None)
    def mousePressEvent(self,event:QMouseEvent):
        if event.button()==Qt.LeftButton:self.model.press(round(event.position().x()),round(event.position().y()));self.update()
    def mouseMoveEvent(self,event:QMouseEvent):self.model.move(round(event.position().x()),round(event.position().y()));self.update()
    def mouseReleaseEvent(self,event:QMouseEvent):
        if event.button()==Qt.LeftButton:self.model.release(round(event.position().x()),round(event.position().y()));self.update();self.roiChanged.emit(self.selected_roi())
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor("#090C12"));left,top,width,height=self.transform.content_rect;target=QRect(round(left),round(top),round(width),round(height));painter.drawPixmap(target,QPixmap.fromImage(self.original));selection=self.model.rectangle
        if selection:
            painter.setBrush(QColor(0,0,0,125));painter.setPen(Qt.NoPen);painter.drawRect(QRect(0,0,self.width(),selection.top()));painter.drawRect(QRect(0,selection.bottom()+1,self.width(),self.height()-selection.bottom()-1));painter.drawRect(QRect(0,selection.top(),selection.left(),selection.height()));painter.drawRect(QRect(selection.right()+1,selection.top(),self.width()-selection.right()-1,selection.height()));painter.setBrush(QColor(70,170,255,45));painter.setPen(QPen(QColor("#55B8FF"),2));painter.drawRect(selection)
        painter.end()

class ROIDialog(QDialog):
    def __init__(self,image_path,parent=None):
        super().__init__(parent);self.setWindowTitle("Select waveform ROI");self.resize(900,620);layout=QVBoxLayout(self);self.viewer=ROIImageLabel(image_path);layout.addWidget(self.viewer,1);self.info=QLabel("Drag over the waveform region, then Apply ROI.");layout.addWidget(self.info);self.viewer.roiChanged.connect(lambda roi:self.info.setText(f"Original image ROI: {roi}" if roi else "No ROI selected"));buttons=QDialogButtonBox();reset=buttons.addButton("Reset ROI",QDialogButtonBox.ResetRole);apply=buttons.addButton("Apply ROI",QDialogButtonBox.AcceptRole);cancel=buttons.addButton(QDialogButtonBox.Cancel);reset.clicked.connect(self.viewer.reset_roi);apply.clicked.connect(self.accept);cancel.clicked.connect(self.reject);layout.addWidget(buttons)
    def roi(self):return self.viewer.selected_roi()
