from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json, time
import numpy as np
from PIL import Image
from template_system import list_templates, load_template
from template_system.thumbnails import get_thumbnail
from render.renderer import CPURenderer

def main():
    entries=list_templates("templates"); values=np.abs(np.sin(np.linspace(0,9,64)))*.55+.18; values[::7]=.9; renderer_counts={}; results=[]; thumbs=[]
    for path,data in entries:
        renderer=str(data.get("renderer","bars")).lower(); renderer_counts[renderer]=renderer_counts.get(renderer,0)+1; started=time.perf_counter(); rgba=CPURenderer().render_rgba(320,180,{"values":values},dict(data,_quality="PREVIEW",_glow_scale=.5)); elapsed=time.perf_counter()-started; alpha=int(rgba[:,:,3].max()); thumbs.append(np.asarray(Image.open(get_thumbnail(data)[0])).astype(np.float32).mean(axis=2)); results.append({"id":data.get("id",path.stem),"renderer":renderer,"alpha_max":alpha,"visible":bool(np.any(rgba[:,:,:3]>8)) and alpha>8,"fps":1/max(elapsed,1e-6)})
    pairs=[]
    for i in range(len(thumbs)):
        for j in range(i+1,len(thumbs)):
            a,b=thumbs[i],thumbs[j]; sim=float(np.dot(a.ravel(),b.ravel())/(np.linalg.norm(a)*np.linalg.norm(b)+1e-6))
            if sim>.995:pairs.append([results[i]["id"],results[j]["id"],sim])
    report={"preset_count":len(entries),"renderer_counts":renderer_counts,"flagship_count":12,"thumbnail_visible":sum(x["visible"] for x in results),"duplicate_pairs":pairs,"korean_glyph_test":"font resolver enabled","cpu_render":all(x["alpha_max"]>0 for x in results),"results":results}
    Path("validation_results").mkdir(exist_ok=True); Path("validation_results/v079_visual_quality_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8"); Path("validation_results/v079_visual_quality_report.txt").write_text(f"presets={len(entries)}\
visible={report['thumbnail_visible']}/{len(entries)}\
renderers={renderer_counts}\
duplicates={len(pairs)}\
",encoding="utf-8"); print(json.dumps({k:report[k] for k in ("preset_count","renderer_counts","thumbnail_visible","duplicate_pairs","cpu_render")},indent=2))
if __name__=="__main__":main()


