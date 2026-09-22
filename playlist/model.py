from __future__ import annotations
import json,uuid
from dataclasses import asdict,dataclass,field
from pathlib import Path
AUDIO_EXTENSIONS={".wav",".mp3",".flac",".m4a",".ogg",".aac",".wma"}
@dataclass
class PlaylistTrack:
    source_path:str
    name:str=""
    duration:float=0.0
    preset:str="01_clean_bars"
    output_format:str="webm"
    status:str="pending"
    output_path:str=""
    export_override:dict=field(default_factory=dict)
    id:str=field(default_factory=lambda:uuid.uuid4().hex)
    missing:bool=False
    def __post_init__(self):
        if not self.name:self.name=Path(self.source_path).stem
        self.missing=not Path(self.source_path).exists()
@dataclass
class PlaylistProject:
    tracks:list[PlaylistTrack]=field(default_factory=list)
    default_preset:str="01_clean_bars"
    default_export:dict=field(default_factory=lambda:{"format":"webm","resolution":"1920x1080","fps":30})
    output_dir:str=""
    version:int=1
    def add_files(self,paths):
        known={str(Path(t.source_path).resolve()) for t in self.tracks}
        for path in paths:
            resolved=str(Path(path).resolve())
            if resolved not in known:self.tracks.append(PlaylistTrack(str(path),preset=self.default_preset,output_format=self.default_export["format"]));known.add(resolved)
    def add_folder(self,path,recursive=False):
        root=Path(path);items=root.rglob("*") if recursive else root.glob("*");self.add_files(sorted(p for p in items if p.suffix.lower() in AUDIO_EXTENSIONS))
    def remove(self,index):
        if 0<=index<len(self.tracks):return self.tracks.pop(index)
    def clear(self):self.tracks.clear()
    def move(self,old,new):
        if old<0 or old>=len(self.tracks) or new<0 or new>=len(self.tracks):return False
        self.tracks.insert(new,self.tracks.pop(old));return True
    def move_up(self,index):return self.move(index,index-1)
    def move_down(self,index):return self.move(index,index+1)
    def reorder(self,ids):
        lookup={t.id:t for t in self.tracks}
        if set(ids)!=set(lookup):raise ValueError("Reorder IDs must match the playlist")
        self.tracks=[lookup[item] for item in ids]
    def apply_preset_to_all(self,preset):
        self.default_preset=preset
        for track in self.tracks:track.preset=preset
    def retry_failed(self):
        for track in self.tracks:
            if track.status in {"failed","cancelled"}:track.status="pending"
    def to_dict(self):return {"version":self.version,"default_preset":self.default_preset,"default_export":self.default_export,"output_dir":self.output_dir,"tracks":[asdict(t) for t in self.tracks]}
    def save(self,path):Path(path).write_text(json.dumps(self.to_dict(),indent=2,ensure_ascii=False),encoding="utf-8")
    @classmethod
    def load(cls,path):
        data=json.loads(Path(path).read_text(encoding="utf-8"));project=cls(default_preset=data.get("default_preset","01_clean_bars"),default_export=data.get("default_export",{}),output_dir=data.get("output_dir",""),version=data.get("version",1))
        project.tracks=[PlaylistTrack(**item) for item in data.get("tracks",[])];return project
