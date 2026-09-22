"""End-to-end codec regression with ffprobe metadata and one-frame duration tolerance."""
from __future__ import annotations
import json,shutil,subprocess,sys,tempfile,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from pipeline.exporter import ExportOptions,render_audio
from template_system import load_template

def ffprobe(path):
    process=subprocess.run([shutil.which("ffprobe"),"-v","error","-show_entries","format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,pix_fmt,duration:stream_tags=alpha_mode","-of","json",str(path)],capture_output=True,text=True,check=True);return json.loads(process.stdout)
def validate_probe(data,width,height,fps,expected):
    video=next(s for s in data["streams"] if s["codec_type"]=="video");audio=next((s for s in data["streams"] if s["codec_type"]=="audio"),None);duration=float(data["format"]["duration"]);video_duration=float(video.get("duration",duration));audio_duration=float(audio.get("duration",duration)) if audio else 0;return {"resolution_ok":(video["width"],video["height"])==(width,height),"fps_ok":video["r_frame_rate"]==f"{fps}/1","audio_present":audio is not None,"video_duration_seconds":video_duration,"audio_duration_seconds":audio_duration,"audio_video_delta_seconds":abs(video_duration-audio_duration),"duration_error_seconds":abs(duration-expected),"duration_within_one_frame":abs(duration-expected)<=1/fps+.01 and abs(video_duration-audio_duration)<=1/fps+.01,"alpha_present":video.get("pix_fmt","").startswith("yuva") or video.get("tags",{}).get("alpha_mode")=="1","video":video,"audio":audio}
def main():
    with tempfile.TemporaryDirectory(prefix="music-wave-") as folder:
        root=Path(folder);sr=44100;seconds=.5;t=np.arange(int(sr*seconds))/sr;pcm=(np.sin(2*np.pi*110*t)*.7*32767).astype("<i2");audio=root/"tone.wav"
        with wave.open(str(audio),"wb") as stream:stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(sr);stream.writeframes(pcm.tobytes())
        template=load_template("templates/01_clean_bars.json");results=[]
        for fmt in ("mp4","webm","mov"):
            target=root/f"smoke.{fmt}";option=ExportOptions(320,180,24,"PREVIEW","CPU",fmt);render=render_audio(audio,target,template,option,logger=lambda *_:None);metadata=ffprobe(target);checks=validate_probe(metadata,320,180,24,seconds);results.append({"format":fmt,"bytes":target.stat().st_size,"frames":render["frames"],"checks":checks})
        print(json.dumps(results))
        if not all(r["checks"]["resolution_ok"] and r["checks"]["fps_ok"] and r["checks"]["audio_present"] and r["checks"]["duration_within_one_frame"] for r in results):raise SystemExit(1)
if __name__=="__main__":main()
