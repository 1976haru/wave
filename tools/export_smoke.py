"""Short end-to-end smoke test for all export containers."""
import json,tempfile,wave,subprocess,shutil
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from pipeline.exporter import ExportOptions,render_audio
from template_system import load_template

def main():
    with tempfile.TemporaryDirectory(prefix="music-wave-") as folder:
        root=Path(folder);sr=44100;t=np.arange(int(sr*.35))/sr;pcm=(np.sin(2*np.pi*110*t)*.7*32767).astype("<i2");audio=root/"tone.wav"
        with wave.open(str(audio),"wb") as stream:stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(sr);stream.writeframes(pcm.tobytes())
        template=load_template("templates/01_clean_bars.json");results=[]
        for fmt in ("mp4","webm","mov"):
            target=root/f"smoke.{fmt}";result=render_audio(audio,target,template,ExportOptions(320,180,24,"PREVIEW","CPU",fmt),logger=lambda *_:None);probe=subprocess.run([shutil.which("ffprobe"),"-v","error","-select_streams","v:0","-show_entries","stream=pix_fmt:stream_tags=alpha_mode","-of","json",str(target)],capture_output=True,text=True,check=True);results.append({"format":fmt,"bytes":target.stat().st_size,"frames":result["frames"],"probe":json.loads(probe.stdout)})
        print(json.dumps(results))
if __name__=="__main__":main()
