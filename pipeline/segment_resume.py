from __future__ import annotations
import hashlib,json,os
from dataclasses import dataclass,asdict
from pathlib import Path

SEGMENT_SECONDS=10.0
@dataclass(frozen=True)
class Segment:
    index:int
    start_frame:int
    end_frame:int
    @property
    def frame_count(self): return self.end_frame-self.start_frame+1

def plan_segments(duration,fps,segment_seconds=SEGMENT_SECONDS):
    total=max(1,int(round(float(duration)*fps))); size=max(1,int(round(segment_seconds*fps))); return [Segment(i,start,min(total-1,start+size-1)) for i,start in enumerate(range(0,total,size))]

def settings_hash(settings):
    payload=json.dumps(settings,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode(); return hashlib.sha256(payload).hexdigest()

def atomic_write_json(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8"); os.replace(tmp,path)

def manifest_for(track_path,duration,fps,settings,segments):
    return {"track_path":str(track_path),"track_duration":float(duration),"fps":int(fps),"resolution":settings.get("resolution"),"preset_id":settings.get("preset_id"),"format":settings.get("format","webm"),"quality":settings.get("quality","BALANCED"),"settings_hash":settings_hash(settings),"segment_seconds":SEGMENT_SECONDS,"total_segments":len(segments),"completed_segments":[],"next_segment":0,"status":"pending"}

def valid_completed_segments(manifest,root):
    valid=[]; root=Path(root)
    for index in manifest.get("completed_segments",[]):
        path=root/f"segment_{int(index):03d}.webm"
        if path.exists() and path.stat().st_size>4:
            try:
                header=path.open("rb").read(4)
                if path.suffix.lower()==".webm" and header!=bytes.fromhex("1a45dfa3"): continue
                valid.append(int(index))
            except OSError: continue
    ordered=[]
    for index in sorted(set(valid)):
        if index != len(ordered): break
        ordered.append(index)
    return ordered

def recover_manifest(manifest_path,current_settings,segment_root):
    path=Path(manifest_path)
    if not path.exists(): return None
    try: manifest=json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError,json.JSONDecodeError): return None
    if manifest.get("settings_hash")!=settings_hash(current_settings): return {"incompatible":True,"manifest":manifest}
    valid=valid_completed_segments(manifest,segment_root); manifest["completed_segments"]=valid; manifest["next_segment"]=(valid[-1]+1 if valid else 0); manifest["status"]="paused" if valid else manifest.get("status","pending"); atomic_write_json(path,manifest); return manifest

def checkpoint(manifest_path,manifest,segment_index,segment_root):
    segment_root=Path(segment_root); segment_root.mkdir(parents=True,exist_ok=True); path=segment_root/f"segment_{int(segment_index):03d}.webm"
    if not path.exists() or path.stat().st_size<=0: return False
    manifest=dict(manifest); done=sorted(set(manifest.get("completed_segments",[])+[int(segment_index)])); manifest["completed_segments"]=done; manifest["next_segment"]=done[-1]+1; manifest["status"]="paused"; atomic_write_json(manifest_path,manifest); return True

def track_resume_paths(output_dir, track_path):
    """Return the private checkpoint directory and manifest path for one track."""
    root=Path(output_dir)/".mws_temp"/Path(track_path).stem
    return root, root/"manifest.json"

def ensure_manifest(output_dir, track_path, duration, fps, settings):
    """Create (or recover) a manifest without touching the final output."""
    root,path=track_resume_paths(output_dir,track_path)
    segments=plan_segments(duration,fps)
    if path.exists():
        recovered=recover_manifest(path,settings,root)
        if recovered is not None: return root,path,recovered,segments
    manifest=manifest_for(track_path,duration,fps,settings,segments)
    atomic_write_json(path,manifest)
    return root,path,manifest,segments




