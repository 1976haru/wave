from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QFileDialog,QHBoxLayout,QInputDialog,QPushButton,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget
from playlist.model import PlaylistProject
class PlaylistTable(QTableWidget):
    dropped=Signal()
    def dropEvent(self,event):super().dropEvent(event);self.dropped.emit()
class PlaylistPanel(QWidget):
    changed=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.project=PlaylistProject();layout=QVBoxLayout(self);self.table=PlaylistTable(0,5);self.table.setHorizontalHeaderLabels(["Track Name","Duration","Preset","Format","Status"]);self.table.setDragDropMode(QTableWidget.InternalMove);self.table.cellChanged.connect(self._cell_changed);self.table.dropped.connect(self._sync_drop);layout.addWidget(self.table)
        for labels in ((("Add Files",self.add_files),("Add Folder",self.add_folder),("Remove",self.remove),("Clear",self.clear)),(("Move Up",self.up),("Move Down",self.down),("Preset to All",self.preset_all)),(("Save Playlist",self.save),("Load Playlist",self.load),("Retry Failed",self.retry_failed))):
            row=QHBoxLayout()
            for text,slot in labels:button=QPushButton(text);button.clicked.connect(slot);row.addWidget(button)
            layout.addLayout(row)
    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.project.tracks))
        for row,track in enumerate(self.project.tracks):
            values=(track.name,f"{track.duration:.1f}s",track.preset,track.output_format,("Missing" if track.missing else track.status))
            for column,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                if column==0:item.setData(Qt.UserRole,track.id)
                if column not in (2,3):item.setFlags(item.flags()&~Qt.ItemIsEditable)
                self.table.setItem(row,column,item)
        self.table.blockSignals(False)
        self.changed.emit(self.project)
    def _cell_changed(self,row,column):
        if row>=len(self.project.tracks):return
        item=self.table.item(row,column)
        if not item:return
        if column==2:self.project.tracks[row].preset=item.text()
        elif column==3 and item.text().lower() in {"mp4","webm","mov"}:self.project.tracks[row].output_format=item.text().lower()
        self.changed.emit(self.project)
    def _sync_drop(self):
        ids=[self.table.item(row,0).data(Qt.UserRole) for row in range(self.table.rowCount()) if self.table.item(row,0)]
        if len(ids)==len(self.project.tracks):self.project.reorder(ids);self.refresh()
    def add_files(self):
        files,_=QFileDialog.getOpenFileNames(self,"Add playlist tracks","","Audio (*.wav *.mp3 *.flac *.m4a *.ogg *.aac *.wma)");self.project.add_files(files);self.refresh()
    def add_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Add audio folder")
        if folder:self.project.add_folder(folder);self.refresh()
    def remove(self):self.project.remove(self.table.currentRow());self.refresh()
    def clear(self):self.project.clear();self.refresh()
    def up(self):row=self.table.currentRow();self.project.move_up(row);self.refresh();self.table.selectRow(max(0,row-1))
    def down(self):row=self.table.currentRow();self.project.move_down(row);self.refresh();self.table.selectRow(min(len(self.project.tracks)-1,row+1))
    def preset_all(self):
        value,ok=QInputDialog.getText(self,"Playlist Preset","Preset name or file",text=self.project.default_preset)
        if ok and value:self.project.apply_preset_to_all(value);self.refresh()
    def retry_failed(self):self.project.retry_failed();self.refresh()
    def save(self):
        path,_=QFileDialog.getSaveFileName(self,"Save Playlist","","Music Wave Playlist (*.mwsplaylist.json)")
        if path:self.project.save(path)
    def load(self):
        path,_=QFileDialog.getOpenFileName(self,"Load Playlist","","Music Wave Playlist (*.mwsplaylist.json)")
        if path:self.project=PlaylistProject.load(path);self.refresh()
