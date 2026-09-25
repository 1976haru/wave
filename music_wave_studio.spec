from PyInstaller.utils.hooks import collect_all
hiddenimports=["moderngl","glcontext","av"]
datas=[("templates","templates"),("resources","resources"),("VERSION.txt",".")]
for package in ("moderngl","av"):
    try:
        package_datas,binaries,imports=collect_all(package);datas+=package_datas;hiddenimports+=imports
    except Exception:pass
a=Analysis(["app.py"],pathex=[],binaries=[],datas=datas,hiddenimports=hiddenimports,hooksconfig={},runtime_hooks=[],excludes=["librosa","numba","llvmlite","matplotlib","pandas","IPython","pytest","tests","tkinter","scipy.stats","scipy.spatial","scipy.sparse","scipy.optimize","scipy.interpolate","scipy.integrate","scipy.cluster","scipy.odr","scipy.io","scipy.ndimage","PySide6.QtWebEngineCore","PySide6.QtWebEngineWidgets","PySide6.QtQuick","PySide6.QtQml","PySide6.Qt3DCore","PySide6.QtBluetooth","PySide6.QtCharts","PySide6.QtDataVisualization","PySide6.QtLocation","PySide6.QtNfc","PySide6.QtPdf","PySide6.QtPositioning","PySide6.QtRemoteObjects","PySide6.QtScxml","PySide6.QtSensors","PySide6.QtSerialBus","PySide6.QtSerialPort","PySide6.QtSpatialAudio","PySide6.QtSql","PySide6.QtTest"],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name="MusicWaveStudio_v0.8.2.7",debug=False,bootloader_ignore_signals=False,strip=False,upx=True,console=False,icon=None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=True,name="MusicWaveStudio_v0.8.2.7")