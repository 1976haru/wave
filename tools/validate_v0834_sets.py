"""Short real encodes covering 15-track SET and two-SET queue semantics."""
from __future__ import annotations
import json,sys,time,tracemalloc,wave
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mws_queue.queue_manager import JobSet,QueueManager
from pipeline.exporter import ExportOptions
from pipeline.set_renderer import render_set
from template_system import load_template

OUT=ROOT/"validation_results/v0834_final_signature/set_validation"
TEMPLATES={"Dual":ROOT/"templates/00_v0834_tokyo_chill_dual.json","His":ROOT/"templates/00_v0834_tokyo_chill_his.json","Her":ROOT/"templates/00_v0834_tokyo_chill_her.json"}

def make_tracks():
    folder=OUT/"fixture_15";folder.mkdir(parents=True,exist_ok=True);sr=8000;duration=.40
    for i in range(15):
        path=folder/f"track_{i+1:02d}.wav";t=np.arange(int(sr*duration))/sr;beat=np.exp(-np.mod(t,.2)*25);pcm=np.clip((.32*np.sin(2*np.pi*(50+i*2)*t)*beat+.12*np.sin(2*np.pi*(180+i*5)*t))*32767,-32768,32767).astype("<i2")
        with wave.open(str(path),"wb") as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes(pcm.tobytes())
    return sorted(folder.glob("*.wav")),duration

def probe(path):
    cap=cv2.VideoCapture(str(path));frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);cap.release();return {"frames":frames,"fps":fps,"duration":frames/fps if fps else 0,"bytes":path.stat().st_size}

def main():
    OUT.mkdir(parents=True,exist_ok=True);files,track_duration=make_tracks();options=ExportOptions(960,160,24,"BALANCED","CPU","mp4",None,"overlay","h264",False,18);report={"track_count":15,"expected_duration":15*track_duration,"main":{},"queue":{}}
    for name,path in TEMPLATES.items():
        target=OUT/f"{name}_15TRACK_SET.mp4";timeline=OUT/f"{name}_timeline.json";started=time.perf_counter();result=render_set(files,target,load_template(path),options,timeline);media=probe(target);timeline_data=json.loads(timeline.read_text(encoding="utf-8"));report["main"][name]={**result,**media,"elapsed":time.perf_counter()-started,"timeline_tracks":len(timeline_data["tracks"]),"duration_error":abs(media["duration"]-15*track_duration),"output_count":1}
    queue_root=OUT/"two_set_queue";queue_root.mkdir(exist_ok=True);state=queue_root/"queue_state.json";manager=QueueManager(state);manager.clear()
    for number,preset in ((1,TEMPLATES["Dual"]),(2,TEMPLATES["His"])):
        track={"audio":str(files[0]),"set_audio_files":[str(p) for p in files],"output_name":f"SET{number:02d}_WAVE.mp4","preset":str(preset),"format":"mp4"}
        manager.add(JobSet(f"SET {number}",[track],preset=str(preset),export={"format":"mp4"},output_dir=str(queue_root)))
    def render(track,job,progress_detail=None):
        return render_set(track["set_audio_files"],Path(job["output_dir"])/track["output_name"],load_template(track["preset"]),options,progress_detail=progress_detail,cancel=lambda:manager.cancel_requested)
    tracemalloc.start();baseline=tracemalloc.get_traced_memory()[0];started=time.perf_counter();result=manager.run(render);elapsed=time.perf_counter()-started;current,peak=tracemalloc.get_traced_memory();tracemalloc.stop();outputs=sorted(queue_root.glob("SET*_WAVE.mp4"))
    report["queue"]={"success":result.success,"sets_success":result.sets_success,"tracks_success":result.tracks_success,"elapsed":elapsed,"peak_memory_mb":round((peak-baseline)/1048576,3),"memory_growth_mb":round((current-baseline)/1048576,3),"outputs":[{"name":p.name,**probe(p)} for p in outputs],"output_count":len(outputs),"manager_running_after":manager.running,"statuses":[x.status for x in manager.sets],"total_music_duration":30*track_duration}
    (OUT/"set_validation_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");(OUT/"set_validation_report.txt").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
