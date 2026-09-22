from __future__ import annotations
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QHBoxLayout,QInputDialog,QLabel,QMessageBox,QPushButton,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget
from workflow.queue_manager import QueueManager
class QueuePanel(QWidget):
    startRequested=Signal()
    changed=Signal()
    def __init__(self,manager=None,parent=None):
        super().__init__(parent);self.manager=manager or QueueManager();layout=QVBoxLayout(self);self.summary=QLabel();layout.addWidget(self.summary);self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(["세트","곡 수","총 시간","스타일","출력","상태","예상"]);self.table.setSelectionBehavior(QTableWidget.SelectRows);layout.addWidget(self.table)
        row=QHBoxLayout()
        for text,slot in (("이름 변경",self.rename),("복제",self.duplicate),("삭제",self.remove),("위로",self.up),("아래로",self.down),("실행 전 검사",self.preflight),("예약 작업 모두 시작",self.startRequested.emit)):
            button=QPushButton(text);button.clicked.connect(slot);row.addWidget(button)
        layout.addLayout(row);self.refresh()
    def refresh(self):
        self.table.setRowCount(len(self.manager.sets));self.summary.setText(f"예약 작업 {len(self.manager.sets)} / {self.manager.max_sets}")
        for row,item in enumerate(self.manager.sets):
            values=(item.name,str(item.total),item.display_duration,item.preset,item.export.get("format","webm"),item.status,f"{item.progress*100:.0f}%")
            for column,value in enumerate(values):self.table.setItem(row,column,QTableWidgetItem(str(value)))
    def selected(self):
        rows=self.table.selectionModel().selectedRows();return rows[0].row() if rows else -1
    def rename(self):
        index=self.selected()
        if index<0:return
        value,ok=QInputDialog.getText(self,"세트 이름","이름",text=self.manager.sets[index].name)
        if ok and value:self.manager.sets[index].name=value;self.manager.save();self.refresh()
    def duplicate(self):
        index=self.selected()
        if index>=0:
            try:self.manager.duplicate(index);self.refresh()
            except ValueError as exc:QMessageBox.warning(self,"예약 작업",str(exc))
    def remove(self):
        index=self.selected()
        if index>=0:self.manager.remove(index);self.refresh()
    def up(self):
        index=self.selected()
        if self.manager.move_up(index):self.refresh();self.table.selectRow(index-1)
    def down(self):
        index=self.selected()
        if self.manager.move_down(index):self.refresh();self.table.selectRow(index+1)
    def preflight(self):
        results=self.manager.preflight();text="\n".join(f"{item['name']}: {'준비 완료' if item['ready'] else '; '.join(item['errors'])}" for item in results);QMessageBox.information(self,"실행 전 검사",text or "예약 작업이 없습니다.")
