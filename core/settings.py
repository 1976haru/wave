from __future__ import annotations
import logging
from PySide6.QtCore import QByteArray,QSettings
from core.runtime_paths import state_dir
class AppSettings:
    KEYS=("last_audio_folder","last_output_folder","last_template","renderer_mode","quality","resolution","fps","ffmpeg_path","splitter_sizes","language","first_run_done","sleep_prevention","completion_action","low_memory_mode")
    def __init__(self,settings=None):
        if settings is None:
            state_dir().mkdir(parents=True,exist_ok=True);settings=QSettings(str(state_dir()/"settings.ini"),QSettings.IniFormat)
        self.settings=settings
    def get(self,key,default=None,type_=None):
        try:return self.settings.value(key,default,type=type_) if type_ else self.settings.value(key,default)
        except (TypeError,ValueError):logging.exception("SETTINGS read failed key=%s",key);return default
    def set(self,key,value):
        if key not in self.KEYS and key!="window_geometry":raise KeyError(key)
        try:self.settings.setValue(key,value)
        except (OSError,TypeError,ValueError):logging.exception("SETTINGS write failed key=%s",key)
    def save_window(self,window):
        try:self.settings.setValue("window_geometry",window.saveGeometry());self.settings.sync()
        except Exception:logging.exception("SETTINGS window save failed")
    def restore_window(self,window):
        try:
            value=self.settings.value("window_geometry")
            if not value:return False
            if isinstance(value,str):value=QByteArray.fromBase64(value.encode("ascii"))
            elif not isinstance(value,QByteArray):value=QByteArray(value)
            return bool(value and window.restoreGeometry(value))
        except Exception:logging.exception("SETTINGS geometry restore failed");return False
    def reset(self):
        try:self.settings.clear();self.settings.sync();return self.settings.status()==QSettings.NoError
        except Exception:logging.exception("SETTINGS reset failed");return False
