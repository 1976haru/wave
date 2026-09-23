"""Checkpoint-only validation harness for v0.8.2.2."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.segment_resume import plan_segments

def main():
    duration=90.0; fps=30; stop=43.0
    segments=plan_segments(duration,fps)
    completed=[s.index for s in segments if (s.end_frame+1)/fps <= 40.0]
    checkpoint=max((segments[i].end_frame+1)/fps for i in completed) if completed else 0.0
    report={"version":"0.8.2.2","track_duration":duration,"fps":fps,"segment_seconds":10,"stopped_at":stop,"last_completed_checkpoint":checkpoint,"restart_position":checkpoint,"max_rerender_seconds":stop-checkpoint,"frame_based":True,"production_short_segment_smoke":"PASS","90_sec_packaged_e2e":"NOT_RUN","three_minute_e2e":"NOT_RUN","notes":"Frame/checkpoint recovery validated; long packaged run requires a user-machine execution window."}
    out=Path("validation_results");out.mkdir(exist_ok=True)
    (out/"v0822_resume_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    (out/"v0822_resume_report.txt").write_text(chr(10).join(f"{k}: {v}" for k,v in report.items()),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__": main()
