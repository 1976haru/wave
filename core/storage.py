import shutil
from pathlib import Path
def disk_space(path):
    target=Path(path)
    while not target.exists() and target.parent!=target:target=target.parent
    usage=shutil.disk_usage(target);return {"total":usage.total,"used":usage.used,"free":usage.free}
def disk_warning(path,minimum_free_gb=5.0):
    info=disk_space(path);info["warning"]=info["free"]<minimum_free_gb*1024**3;return info
