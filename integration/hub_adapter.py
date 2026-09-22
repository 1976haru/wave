from __future__ import annotations
import json,subprocess,sys
from pathlib import Path
class HubAdapter:
    """Process boundary used by Playlist Studio Hub; no Hub internals are assumed."""
    def __init__(self,executable=None):self.executable=str(executable) if executable else sys.executable
    def command(self,job_path):
        if Path(self.executable).suffix.lower()==".exe" and Path(self.executable).name.lower()!="python.exe":return [self.executable,"--headless","--job",str(job_path)]
        return [self.executable,str(Path(__file__).parents[1]/"app.py"),"--headless","--job",str(job_path)]
    def run(self,job_path,check=False):return subprocess.run(self.command(job_path),capture_output=True,text=True,check=check)
    @staticmethod
    def create_job(path,tracks,output_dir,**defaults):
        data={"contract_version":1,"tracks":tracks,"output_dir":str(output_dir),**defaults};Path(path).write_text(json.dumps(data,indent=2),encoding="utf-8");return data
