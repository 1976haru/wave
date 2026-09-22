"""Deterministic long-session preview scheduling validation."""
from __future__ import annotations
import argparse,json,random,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from preview.scheduler import FrameScheduler

def simulate(duration,fps=24,poll_hz=120,seed=52):
    random.seed(seed);scheduler=FrameScheduler(fps);wall=0;audio=0;scheduler.reset(0,0);poll=1/poll_hz
    while audio<duration:
        jitter=random.uniform(-.0015,.0015);stall=.075 if random.random()<.002 else 0;wall+=max(.001,poll+jitter)+stall;audio=wall;scheduler.should_render(audio,wall)
    metrics=scheduler.metrics;expected=int(duration*fps);return {"duration_seconds":duration,"target_fps":fps,"average_fps":metrics.rendered_frames/duration,"rendered_frames":metrics.rendered_frames,"expected_frames":expected,"dropped_frames":metrics.dropped_frames,"drop_ratio":metrics.dropped_frames/max(1,expected),"max_drift_ms":metrics.max_drift*1000}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",default="validation_results/preview_timing.json");args=parser.parse_args();report={"sessions":[simulate(value) for value in (10,30,60)]};target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report,indent=2))
if __name__=="__main__":main()
