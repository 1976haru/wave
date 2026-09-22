from PyInstaller.utils.hooks import collect_all
hiddenimports=[]
datas=[("templates","templates")]
for package in ("moderngl","av","cv2","PySide6"):
    try:
        package_datas,binaries,imports=collect_all(package);datas+=package_datas;hiddenimports+=imports
    except Exception:pass
a=Analysis(["app.py"],pathex=[],binaries=[],datas=datas,hiddenimports=hiddenimports,hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name="MusicWaveStudio",debug=False,bootloader_ignore_signals=False,strip=False,upx=True,console=False,icon=None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=True,name="MusicWaveStudio")
