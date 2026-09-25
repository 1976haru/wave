from __future__ import annotations
import argparse,json,time
from pathlib import Path
from integration.job_contract import load_job,validate_job,write_result
from pipeline.exporter import ExportOptions,output_extension,render_audio
from template_system import load_template
from core.paths import resource_path
def resolve_template(value):
    path=Path(str(value))
    if path.is_file():return load_template(path)
    slug=str(value).lower().replace(" ","_")
    candidates=list(resource_path("templates").glob("*.json"))
    for candidate in candidates:
        template=load_template(candidate)
        aliases={candidate.stem.lower(),str(template.get("name","")).lower().replace(" ","_"),str(template.get("id","")).lower()}
        if slug in aliases or candidate.stem.endswith(slug):return template
    raise FileNotFoundError(f"Template not found: {value}")
def run_job(job_or_path,result_path=None,render_fn=render_audio):
    job=load_job(job_or_path) if isinstance(job_or_path,(str,Path)) else validate_job(job_or_path);started=time.perf_counter();output_dir=Path(job["output_dir"]);output_dir.mkdir(parents=True,exist_ok=True);results=[]
    for item in job["tracks"]:
        source=Path(item["audio"]);record={"audio":str(source),"status":"failed"}
        try:
            if not source.exists():raise FileNotFoundError(f"Missing source track: {source}")
            template=resolve_template(item["preset"]);fmt=item["format"];override={**job.get("export",{}),**item.get("export",{})};profile=template.get("canvas_profile",{}) if template.get("category") in {"chill_rap_signature","signature_experimental_v2","signature_experimental_v3"} else {}
            resolution=override.pop("resolution","SIGNATURE" if profile else "1920x1080")
            if profile and resolution=="SIGNATURE":override={"width":profile.get("width",960),"height":profile.get("height",160),"fps":profile.get("fps",24),"crf":18,**override}
            options=ExportOptions.from_resolution(resolution,format=fmt,**{k:v for k,v in override.items() if k in {"fps","quality","renderer","width","height","ffmpeg_path","crf","video_codec","include_audio","canvas_mode"}})
            target=Path(item.get("output") or output_dir/(source.stem+output_extension(fmt)));details=render_fn(source,target,template,options)
            record.update(status="success",output=str(target),details=details or {})
        except Exception as exc:record["error"]=str(exc)
        results.append(record)
    result={"contract_version":1,"success":sum(x["status"]=="success" for x in results),"failed":sum(x["status"]=="failed" for x in results),"outputs":[x.get("output") for x in results if x.get("output")],"render_time":time.perf_counter()-started,"tracks":results,"errors":[x["error"] for x in results if x.get("error")]}
    target=Path(result_path or job.get("result_path") or output_dir/"result.json");write_result(target,result);return result
def main(argv=None):
    parser=argparse.ArgumentParser(description="Music Wave Studio headless renderer");parser.add_argument("job",nargs="?");parser.add_argument("--job",dest="job_option");args=parser.parse_args(argv);result=run_job(args.job_option or args.job);print(json.dumps(result,ensure_ascii=False));return 0 if not result["failed"] else 2
if __name__=="__main__":raise SystemExit(main())
