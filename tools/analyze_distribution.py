from __future__ import annotations
import argparse,json
from pathlib import Path
def analyze(path):
    root=Path(path);groups={}
    for file in root.rglob("*"):
        if file.is_file():
            relative=file.relative_to(root);group=relative.parts[0] if len(relative.parts)>1 else relative.name;groups[group]=groups.get(group,0)+file.stat().st_size
    return {"path":str(root),"total_bytes":sum(groups.values()),"largest":[{"name":k,"bytes":v} for k,v in sorted(groups.items(),key=lambda x:x[1],reverse=True)]}
def main():
    p=argparse.ArgumentParser();p.add_argument("path",nargs="?",default="dist/MusicWaveStudio");p.add_argument("--output",default="validation_results/distribution_size.json");a=p.parse_args();report=analyze(a.path);Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report,indent=2))
if __name__=="__main__":main()
