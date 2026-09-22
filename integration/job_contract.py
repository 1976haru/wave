from __future__ import annotations
import json
from pathlib import Path
SUPPORTED_FORMATS={"mp4","webm","mov"}
def validate_job(data):
    if not isinstance(data,dict):raise ValueError("Job must be a JSON object")
    tracks=data.get("tracks")
    if not isinstance(tracks,list) or not tracks:raise ValueError("Job requires at least one track")
    output_dir=data.get("output_dir")
    if not output_dir:raise ValueError("Job requires output_dir")
    default_format=str(data.get("format","webm")).lower()
    if default_format not in SUPPORTED_FORMATS:raise ValueError(f"Unsupported format: {default_format}")
    normalized={**data,"format":default_format,"output_dir":str(output_dir),"tracks":[]}
    for index,item in enumerate(tracks):
        if isinstance(item,str):item={"audio":item}
        if not isinstance(item,dict) or not item.get("audio"):raise ValueError(f"Track {index+1} requires audio")
        fmt=str(item.get("format",default_format)).lower()
        if fmt not in SUPPORTED_FORMATS:raise ValueError(f"Unsupported format for track {index+1}: {fmt}")
        normalized["tracks"].append({**item,"audio":str(item["audio"]),"format":fmt,"preset":item.get("preset",data.get("preset","01_clean_bars"))})
    return normalized
def load_job(path):return validate_job(json.loads(Path(path).read_text(encoding="utf-8-sig")))
def write_result(path,result):Path(path).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
