from __future__ import annotations
import os,sys
from pathlib import Path

def version_file():
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    return base/'VERSION.txt'

def get_version():
    try:
        return version_file().read_text(encoding='utf-8-sig').strip().splitlines()[0]
    except (OSError,IndexError):
        return '0.0.0'

def build_info():
    return {'version':get_version(),'commit':os.environ.get('MWS_COMMIT','unknown'),'executable':str(Path(sys.executable).resolve()),'build':os.environ.get('MWS_BUILD_TIMESTAMP','unknown')}

