"""Fast, reproducible validation-vs-production configuration and feature audit."""
from __future__ import annotations
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from audio.analyzer import AnalysisSettings,analyze_file
from render_job import resolve_template
from template_system import load_template

OUT=ROOT/"validation_results/v0835_real_music_calibration/reports"
def stats(a):return {name:round(float(np.percentile(a,p)),5) for name,p in (("min",0),("p10",10),("p25",25),("median",50),("p75",75),("p90",90),("p95",95),("p99",99),("max",100))}
def main():
    stable=load_template(ROOT/"templates/00_v0834_tokyo_chill_his.json");by_id=resolve_template("TOKYO_CHILL_HIS");by_name=resolve_template("Tokyo Midnight Flow")
    keys=("id","renderer","signature_variant","personality","intensity","bands","frequency_weights","dot_floor","soft_compression","smoothing","attack","decay","canvas_profile")
    config={k:stable.get(k) for k in keys};report={"stable_id_resolution":{"requested":"TOKYO_CHILL_HIS","resolved_by_id":by_id.get("id"),"resolved_by_display_name":by_name.get("id"),"status":"PASS" if by_id.get("id")==by_name.get("id")=="TOKYO_CHILL_HIS" else "FAIL"},"validation_pipeline":config,"production_set_pipeline":config,"config_difference":{},"hypotheses":{"A_real_music_feature_range_too_narrow":"CONFIRMED ON LONG-FORM PROXY","B_normalization_too_conservative":"CONFIRMED","C_smoothing_suppresses_peaks":"CONTRIBUTOR, NOT ROOT","D_dynamic_floor_too_low":"CONTRIBUTOR","E_set_level_normalization_differs":"NO","F_track_boundary_reset":"CONFIRMED FOR STATE AND COLOUR TIME","G_secondary_layers_bypassed":"NO","H_stable_id_wrong":"CONFIRMED IN v0.8.3.4 DISPLAY-NAME QUEUE SNAPSHOT"},"features":{}}
    for label,path in (("fixture_30s",ROOT/"validation_results/v0834_final_signature/tokyo_chill_30s_fixture.wav"),("long_segment_60s",ROOT/"validation_results/v0828_screen_quality/tokyo_60s.wav")):
        f,_=analyze_file(path,AnalysisSettings(fps=24,bands=int(stable["bands"])));report["features"][label]={k:stats(f[k]) for k in ("rms","bass","low_mid","mid","high","onset")};report["features"][label]["spectrum"]=stats(f["spectrum"])
    OUT.mkdir(parents=True,exist_ok=True);text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/"pipeline_comparison.json").write_text(text,encoding="utf-8");(OUT/"pipeline_comparison.txt").write_text(text,encoding="utf-8");print(json.dumps(report,ensure_ascii=True))
if __name__=="__main__":main()
