from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from audio.analyzer import analyze_pcm,decode_audio
from audio.experimental import analyze_librosa,librosa_available
def metrics(features):
    onset=np.asarray(features["onset"]);bass=np.asarray(features["bass"]);high=np.asarray(features["high"]);spectrum=np.asarray(features["spectrum"])
    return {"onset_count":int(np.sum(onset>.55)),"onset_responsiveness":float(np.percentile(onset,95)),"temporal_jitter":float(np.mean(np.abs(np.diff(spectrum,axis=0)))),"low_band_separation":float(np.mean(np.abs(bass-np.asarray(features["mid"])))),"high_band_sensitivity":float(np.percentile(high,90)),"silent_floor_stability":float(1-np.clip(np.percentile(features["rms"],10),0,1)),"dynamic_range_usage":float(np.percentile(spectrum,95)-np.percentile(spectrum,5))}
def preview(features,path):
    values=features["spectrum"][min(len(features["spectrum"])-1,len(features["spectrum"])//2)];image=Image.new("RGBA",(640,240),(8,11,16,255));draw=ImageDraw.Draw(image);width=640/len(values)
    for i,value in enumerate(values):draw.rectangle((i*width,240-value*210,(i+1)*width-1,240),fill=(80,190,255,230))
    image.save(path)
def compare(audio,output="analysis_comparison",seconds=30):
    root=Path(output);root.mkdir(parents=True,exist_ok=True);pcm,sr=decode_audio(audio);pcm=pcm[:int(sr*seconds)];report={"audio":str(audio),"sample_rate":sr,"duration":len(pcm)/sr,"analyzers":{}}
    for name,backend,mapping in (("numpy","NUMPY","LOG"),("scipy","SCIPY","PERCEPTUAL")):
        started=time.perf_counter();features=analyze_pcm(pcm,sr,analyzer_backend=backend,spectrum_mapping=mapping);folder=root/name;folder.mkdir(exist_ok=True);preview(features,folder/"preview_midpoint.png");report["analyzers"][name]={"analysis_time":time.perf_counter()-started,"cache_size_estimate":sum(x.nbytes for x in features.values() if hasattr(x,"nbytes")),"metrics":metrics(features)}
    report["librosa"]={"available":librosa_available()}
    if librosa_available():
        started=time.perf_counter();data=analyze_librosa(pcm,sr);report["librosa"].update(analysis_time=time.perf_counter()-started,features=list(data))
    (root/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8");lines=["Music Wave Studio analyzer comparison",f"Audio: {audio}"]
    for name,data in report["analyzers"].items():lines.append(f"{name}: {data['analysis_time']:.3f}s, jitter={data['metrics']['temporal_jitter']:.5f}")
    lines.append(f"librosa available: {report['librosa']['available']}");(root/"report.txt").write_text("\n".join(lines),encoding="utf-8");return report
def main():
    p=argparse.ArgumentParser();p.add_argument("audio");p.add_argument("--output",default="analysis_comparison");p.add_argument("--seconds",type=int,default=30);a=p.parse_args();compare(a.audio,a.output,a.seconds)
if __name__=="__main__":main()
