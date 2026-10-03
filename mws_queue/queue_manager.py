from __future__ import annotations
import copy,json,logging,os,shutil,sys,time,uuid
from datetime import datetime
from dataclasses import asdict,dataclass,field
from pathlib import Path
from core.runtime_paths import queue_state_path
from pipeline.segment_resume import recover_manifest
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
    def from_dict(cls,data):
        if not isinstance(data,dict):raise TypeError("queue set must be an object")
        values={k:v for k,v in data.items() if k in cls.__dataclass_fields__}
        if not isinstance(values.get("name"),str) or not values["name"].strip():raise ValueError("queue set name is invalid")
        tracks=values.get("tracks")
        if not isinstance(tracks,list) or any(not isinstance(track,dict) for track in tracks):raise ValueError("queue tracks are invalid")
        status=values.get("status","pending")
        if status not in {"pending","running","completed","failed","cancelled"}:raise ValueError("queue status is invalid")
        if not isinstance(values.get("export",{}),dict):raise ValueError("queue export is invalid")
        for key in ("output_dir","preset","id","error"):
            if key in values and values[key] is None:values.pop(key)
        for key in ("completed","failed"):
            if key in values:
                values[key]=max(0,int(values[key]))
        return cls(**values)
@dataclass
class QueueResult:
    sets_total:int
    sets_success:int
    sets_failed:int
    tracks_success:int
    tracks_failed:int
    elapsed:float
    errors:list[str]=field(default_factory=list)
    completed_removed:int=0
    @property
    def success(self):return self.sets_failed==0 and not self.errors
class QueueManager:
    max_sets=5
    def __init__(self,state_path=None,load_state=True,migrate=True):
        self.state_path=Path(state_path) if state_path is not None else queue_state_path();self.sets:list[JobSet]=[];self.running=False;self.cancel_requested=False;self.pause_requested=False;self.load_warning=None
        if load_state:
            if migrate and state_path is None:self._migrate_legacy_state()
            self.load()

    def _legacy_candidates(self):
        executable_dir=Path(sys.executable).resolve().parent
        candidates=[Path.cwd()/"queue_state.json",executable_dir/"queue_state.json",executable_dir.parent/"queue_state.json"]
        unique=[]
        for candidate in candidates:
            if candidate.resolve()!=self.state_path.resolve() and candidate not in unique:unique.append(candidate)
        return unique

    def _migrate_legacy_state(self):
        if self.state_path.exists():return
        for source in self._legacy_candidates():
            if not source.is_file():continue
            try:
                raw=json.loads(source.read_text(encoding="utf-8-sig"));sets=self._decode_sets(raw)
                self.sets=sets
                if not self.save():raise OSError("could not write migrated queue state")
                stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
                backup=source.with_name(f"queue_state_migrated_backup_{stamp}.json")
                shutil.copy2(source,backup)
                logging.info("QUEUE migration source=%s target=%s backup=%s sets=%d",source,self.state_path,backup,len(sets))
                return
            except Exception:
                logging.exception("QUEUE legacy migration failed source=%s",source)

    def _decode_sets(self,data):
        if not isinstance(data,dict) or not isinstance(data.get("sets",[]),list):raise TypeError("queue state root is invalid")
        result=[]
        for raw in data.get("sets",[]):
            item=JobSet.from_dict(raw)
            if item.status=="completed":continue
            if item.status=="running":item.status="pending"
            result.append(item)
        return result[:self.max_sets]
    def add(self,job_set):
        self.prune_completed(save=False)
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
    def prune_completed(self,save=True):
        before=len(self.sets)
        self.sets=[item for item in self.sets if item.status!="completed"]
        removed=before-len(self.sets)
        if removed and save:self.save()
        return removed
    def save(self):
        temp=self.state_path.with_name(self.state_path.name+".tmp")
        try:
            self.state_path.parent.mkdir(parents=True,exist_ok=True);payload={"version":1,"sets":[item.snapshot() for item in self.sets]}
            with open(temp,"w",encoding="utf-8",newline="\n") as handle:
                json.dump(payload,handle,indent=2,ensure_ascii=False);handle.flush();os.fsync(handle.fileno())
            os.replace(temp,self.state_path)
            return True
        except (OSError,TypeError,ValueError):
            logging.exception("QUEUE state save failed path=%s",self.state_path)
            try:temp.unlink(missing_ok=True)
            except OSError:pass
            return False
    def load(self):
        if not self.state_path.exists():return
        try:
            data=json.loads(self.state_path.read_text(encoding="utf-8-sig"));loaded=data.get("sets",[]) if isinstance(data,dict) else None
            self.sets=self._decode_sets(data)
            if len(self.sets)!=len(loaded) or any(isinstance(raw,dict) and raw.get("status")=="running" for raw in loaded):self.save()
        except (OSError,UnicodeDecodeError,json.JSONDecodeError,TypeError,ValueError,KeyError):
            logging.exception("QUEUE corrupt state path=%s",self.state_path);self.sets=[];stamp=datetime.now().strftime("%Y%m%d_%H%M%S");quarantine=self.state_path.with_name(f"queue_state.corrupt.{stamp}.json")
            try:os.replace(self.state_path,quarantine);logging.warning("QUEUE corrupt state quarantined path=%s",quarantine)
            except OSError:logging.exception("QUEUE corrupt state quarantine failed path=%s",self.state_path)
            self.load_warning="예약 작업 파일이 손상되어 격리했습니다. 빈 예약 목록으로 시작합니다."
    def preflight(self,check_template=None):
        results=[]
        for item in self.sets:
            errors=[]
            for track in item.tracks:
                sources=[Path(p) for p in track.get("set_audio_files",[])] or [Path(track.get("audio",track.get("source_path","")))]
                for source in sources:
                    if not source.exists():errors.append(f"{source.name}: ?? ?? ??")
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
    def cancel(self):self.request_cancel()
    def request_pause(self):self.pause_requested=True
    def resume(self):self.pause_requested=False
    def run(self,render_track,progress=None,skip_completed=True,sleep_guard=None,progress_detail=None,reset_cancel=True,between_sets=None):
        started=time.perf_counter();sets_total=len(self.sets);self.running=True
        if reset_cancel:self.cancel_requested=False
        errors=[];tracks_success=tracks_failed=sets_success=sets_failed=0;ran_any=False
        if sleep_guard:sleep_guard.__enter__()
        try:
            for set_index,item in enumerate(self.sets):
                if self.cancel_requested:break
                if item.status=="completed" and skip_completed:continue
                # SET boundary: cleanup / cool-down / memory guard before every SET after the first.
                if between_sets and ran_any:between_sets(set_index+1)
                if self.cancel_requested:break
                ran_any=True
                item.status="running";item.error="";item.completed=0;item.failed=0;self.save()
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
        completed_removed=self.prune_completed(save=True)
        return QueueResult(sets_total,sets_success,sets_failed,tracks_success,tracks_failed,time.perf_counter()-started,errors,completed_removed)

