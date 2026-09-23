from __future__ import annotations
import copy,json,shutil,time,uuid
from dataclasses import asdict,dataclass,field
from pathlib import Path
@dataclass
class JobSet:
    name:str
    tracks:list[dict]
    preset:str="01_clean_bars"
    export:dict=field(default_factory=lambda:{"format":"webm","resolution":"1920x1080","fps":30,"quality":"BALANCED","renderer":"AUTO"})
    output_dir:str="output"
    status:str="pending"
    id:str=field(default_factory=lambda:uuid.uuid4().hex)
    completed:int=0
    failed:int=0
    error:str=""
    created_at:float=field(default_factory=time.time)
    def snapshot(self):
        data=asdict(self);data["tracks"]=copy.deepcopy(self.tracks);return data
    @property
    def total(self):return len(self.tracks)
    @property
    def progress(self):return (self.completed+self.failed)/self.total if self.total else 0.0
    @property
    def display_duration(self):
        seconds=sum(float(t.get("duration",0) or 0) for t in self.tracks);hours,rem=divmod(int(seconds),3600);minutes,_=divmod(rem,60)
        return f"{hours}시간 {minutes}분" if hours else f"{minutes}분"
    @classmethod
    def from_dict(cls,data):return cls(**{k:v for k,v in data.items() if k in cls.__dataclass_fields__})
@dataclass
class QueueResult:
    sets_total:int
    sets_success:int
    sets_failed:int
    tracks_success:int
    tracks_failed:int
    elapsed:float
    errors:list[str]=field(default_factory=list)
    @property
    def success(self):return self.sets_failed==0 and not self.errors
class QueueManager:
    max_sets=5
    def __init__(self,state_path="queue_state.json"):
        self.state_path=Path(state_path);self.sets:list[JobSet]=[];self.running=False;self.cancel_requested=False;self.pause_requested=False;self.load()
    def add(self,job_set):
        if len(self.sets)>=self.max_sets:raise ValueError("최대 5개의 예약 작업만 추가할 수 있습니다.")
        if isinstance(job_set,dict):job_set=JobSet.from_dict(job_set)
        self.sets.append(job_set);self.save();return job_set
    def remove(self,index):
        if not 0<=index<len(self.sets):return None
        removed=self.sets.pop(index);self.save();return removed
    def duplicate(self,index):
        source=self.sets[index];clone=JobSet.from_dict(source.snapshot());clone.id=uuid.uuid4().hex;clone.name=f"{source.name} 복사";clone.status="pending";clone.completed=clone.failed=0;self.add(clone);return clone
    def move(self,old,new):
        if not 0<=old<len(self.sets) or not 0<=new<len(self.sets):return False
        self.sets.insert(new,self.sets.pop(old));self.save();return True
    def move_up(self,index):return self.move(index,index-1) if index>0 else False
    def move_down(self,index):return self.move(index,index+1) if index<len(self.sets)-1 else False
    def clear(self):self.sets.clear();self.save()
    def save(self):
        self.state_path.parent.mkdir(parents=True,exist_ok=True);payload={"version":1,"sets":[item.snapshot() for item in self.sets]};temp=self.state_path.with_suffix(".tmp");temp.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8");temp.replace(self.state_path)
    def load(self):
        if not self.state_path.exists():return
        try:
            data=json.loads(self.state_path.read_text(encoding="utf-8-sig"));self.sets=[JobSet.from_dict(item) for item in data.get("sets",[])][:self.max_sets]
            for item in self.sets:
                if item.status=="running":item.status="pending"
        except (OSError,json.JSONDecodeError,TypeError):self.sets=[]
    def preflight(self,check_template=None):
        results=[]
        for item in self.sets:
            errors=[]
            for track in item.tracks:
                source=Path(track.get("audio",track.get("source_path","")))
                if not source.exists():errors.append(f"{source.name}: 음원 파일 없음")
                if check_template:
                    try:check_template(track.get("preset",item.preset))
                    except Exception as exc:errors.append(str(exc))
            output=Path(item.output_dir)
            try:output.mkdir(parents=True,exist_ok=True);probe=output/".mws_write_test";probe.write_text("ok",encoding="utf-8");probe.unlink()
            except Exception as exc:errors.append(f"출력 폴더: {exc}")
            try:
                if shutil.disk_usage(output).free<512*1024*1024:errors.append("출력 공간 부족(512MB 미만)")
            except OSError as exc:errors.append(str(exc))
            results.append({"id":item.id,"name":item.name,"ready":not errors,"errors":errors})
        return results
    def request_cancel(self):self.cancel_requested=True;self.pause_requested=False
    def request_pause(self):self.pause_requested=True
    def resume(self):self.pause_requested=False
    def run(self,render_track,progress=None,skip_completed=True,sleep_guard=None,progress_detail=None):
        started=time.perf_counter();self.running=True;self.cancel_requested=False;errors=[];tracks_success=tracks_failed=sets_success=sets_failed=0
        if sleep_guard:sleep_guard.__enter__()
        try:
            for set_index,item in enumerate(self.sets):
                if self.cancel_requested:break
                if item.status=="completed" and skip_completed:continue
                item.status="running";item.error="";self.save()
                for track_index,track in enumerate(item.tracks):
                    if self.cancel_requested:break
                    if track.get("status")=="completed" and skip_completed:tracks_success+=1;item.completed+=1;continue
                    try:
                        track_kwargs={}
                        if progress_detail: track_kwargs["progress_detail"]=lambda event, si=set_index+1, ti=track_index+1, item_total=len(item.tracks): progress_detail({**event,"set_index":si,"track_index":ti,"set_total":len(self.sets),"track_total":item_total})
                        result=render_track(copy.deepcopy(track),item.snapshot(),**track_kwargs);track.update(result or {},status="completed",error="");item.completed+=1;tracks_success+=1
                    except Exception as exc:
                        message=f"{item.name}: {track.get('audio',track.get('source_path',''))}: {exc}";track.update(status="failed",error=str(exc));item.failed+=1;tracks_failed+=1;errors.append(message)
                    self.save()
                    if progress:progress(set_index+1,len(self.sets),track_index+1,len(item.tracks),item)
                if self.cancel_requested:item.status="cancelled"
                elif item.failed:item.status="failed";item.error=f"{item.failed}개 트랙 실패";sets_failed+=1
                else:item.status="completed";sets_success+=1
                self.save()
        finally:
            self.running=False
            if sleep_guard:sleep_guard.__exit__(None,None,None)
            self.save()
        return QueueResult(len(self.sets),sets_success,sets_failed,tracks_success,tracks_failed,time.perf_counter()-started,errors)


