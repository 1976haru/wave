from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout,QInputDialog,QLabel,QMessageBox,QPushButton,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget,QFrame
from mws_queue.queue_manager import QueueManager
class QueuePanel(QWidget):
    startRequested=Signal(); changed=Signal()
    def __init__(self,manager=None,parent=None):
        super().__init__(parent);self.manager=manager or QueueManager();layout=QVBoxLayout(self);self.summary=QLabel();self.summary.setStyleSheet("font-size:18px;font-weight:bold;padding:8px");layout.addWidget(self.summary);self.cards=QVBoxLayout();layout.addLayout(self.cards);self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(["??","? ?","? ??","???","??","??","??"]);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.hide();layout.addWidget(self.table)
        row=QHBoxLayout();self.add_button=QPushButton("? ?? ?? ??");self.start_button=QPushButton("?? ??");self.start_button.setMinimumHeight(44);self.start_button.clicked.connect(self.startRequested.emit);row.addWidget(self.add_button);row.addWidget(self.start_button);layout.addLayout(row);self.refresh()
    def refresh(self):
        while self.cards.count(): item=self.cards.takeAt(0); widget=item.widget(); widget and widget.deleteLater()
        self.table.setRowCount(len(self.manager.sets));self.summary.setText(f"?? ?? {len(self.manager.sets)} / {self.manager.max_sets}")
        for row,item in enumerate(self.manager.sets):
            card=QFrame();card.setFrameShape(QFrame.StyledPanel);card.setStyleSheet("QFrame{background:#181E27;border:1px solid #394657;border-radius:8px;padding:8px}");box=QVBoxLayout(card);box.addWidget(QLabel(f"?? {row+1}  |  {item.name}"));box.addWidget(QLabel(f"?: {item.total}?    ? ??: {item.display_duration}    ???: {item.preset}"));box.addWidget(QLabel(f"??: {item.export.get('format','webm').upper()} ??    ??: {item.output_dir}    ??: {item.status}    ??: {item.progress*100:.0f}%"));self.cards.addWidget(card)
            values=(item.name,str(item.total),item.display_duration,item.preset,item.export.get("format","webm"),item.status,f"{item.progress*100:.0f}%")
            for column,value in enumerate(values):self.table.setItem(row,column,QTableWidgetItem(str(value)))
        self.start_button.setEnabled(bool(self.manager.sets));self.changed.emit()
    def selected(self):
        rows=self.table.selectionModel().selectedRows();return rows[0].row() if rows else (0 if self.manager.sets else -1)
    def rename(self):
        index=self.selected();
        if index<0:return
        value,ok=QInputDialog.getText(self,"?? ??","??",text=self.manager.sets[index].name)
        if ok and value:self.manager.sets[index].name=value;self.manager.save();self.refresh()
    def duplicate(self):
        index=self.selected()
        if index>=0:
            try:self.manager.duplicate(index);self.refresh()
            except ValueError as exc:QMessageBox.warning(self,"?? ??",str(exc))
    def remove(self):
        index=self.selected()
        if index>=0:self.manager.remove(index);self.refresh()
    def up(self):
        index=self.selected()
        if self.manager.move_up(index):self.refresh()
    def down(self):
        index=self.selected()
        if self.manager.move_down(index):self.refresh()
    def preflight(self):
        results=self.manager.preflight();text="\n".join(f"{item['name']}: {'?? ??' if item['ready'] else '; '.join(item['errors'])}" for item in results);QMessageBox.information(self,"?? ? ??",text or "?? ??? ????.")
