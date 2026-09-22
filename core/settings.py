from __future__ import annotations
from PySide6.QtCore import QByteArray,QSettings
class AppSettings:
    KEYS=("last_audio_folder","last_output_folder","last_template","renderer_mode","quality","resolution","fps","ffmpeg_path","splitter_sizes")
    def __init__(self,settings=None):self.settings=settings or QSettings("MusicWaveStudio","MusicWaveStudio")
    def get(self,key,default=None,type_=None):return self.settings.value(key,default,type=type_) if type_ else self.settings.value(key,default)
    def set(self,key,value):
        if key not in self.KEYS and key!="window_geometry":raise KeyError(key)
        self.settings.setValue(key,value)
    def save_window(self,window):self.settings.setValue("window_geometry",window.saveGeometry())
    def restore_window(self,window):
        value=self.settings.value("window_geometry")
        return bool(value and window.restoreGeometry(value if isinstance(value,QByteArray) else QByteArray(value)))
