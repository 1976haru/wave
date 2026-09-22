from __future__ import annotations
import json
from pathlib import Path
DEFAULT_TEMPLATE={"version":"0.5.1","name":"Default","renderer":"bars","bands":64,"color":"#FFFFFF","gradient":False,"gradient_start":"#FFFFFF","gradient_end":"#80C8FF","opacity":1.0,"position":"bottom","width":.72,"height":.22,"bar_width":.55,"gap":.45,"roundness":.5,"glow":True,"glow_strength":.55,"glow_radius":10,"shadow":False,"mirror":False,"response":1.25,"attack":.45,"decay":.86,"smoothing":.15,"onset_boost":.1,"bass_weight":1.0,"mid_weight":1.0,"high_weight":1.0}
def migrate_template(data):
    result=dict(DEFAULT_TEMPLATE); old=dict(data); aliases={"style":"renderer","band_count":"bands","barWidth":"bar_width","glowRadius":"glow_radius","glowStrength":"glow_strength","onsetBoost":"onset_boost","bassWeight":"bass_weight","midWeight":"mid_weight","highWeight":"high_weight","gradientStart":"gradient_start","gradientEnd":"gradient_end"}
    for source,target in aliases.items():
        if source in old and target not in old: old[target]=old.pop(source)
    if "colour" in old and "color" not in old: old["color"]=old.pop("colour")
    if old.get("gradient") and not old.get("gradient_start"): old["gradient_start"]=old.get("color",result["color"])
    result.update(old); result["version"]="0.5.1"; result["renderer"]=str(result["renderer"]).lower(); return result
def load_template(path): return migrate_template(json.loads(Path(path).read_text(encoding="utf-8")))
def save_template(path,data):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(migrate_template(data),indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); return target
def list_templates(*directories):
    found=[]
    for directory in directories:
        root=Path(directory)
        if root.exists(): found.extend((p,load_template(p)) for p in sorted(root.glob("*.json")))
    return found
