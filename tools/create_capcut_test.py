"""Create three short files for manual CapCut compatibility validation."""
from __future__ import annotations
import argparse,wave,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from pipeline.exporter import ExportOptions,render_audio
from template_system import load_template

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--seconds",type=float,default=6);parser.add_argument("--output",default="validation_results/capcut_test");args=parser.parse_args();root=Path(args.output);root.mkdir(parents=True,exist_ok=True);sr=44100;t=np.arange(int(sr*args.seconds))/sr;signal=(np.sin(2*np.pi*110*t)*.55+np.sin(2*np.pi*440*t)*.2)*(1+np.sin(2*np.pi*2*t))*.5;audio=root/"source.wav"
    with wave.open(str(audio),"wb") as stream:stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(sr);stream.writeframes(np.clip(signal*32767,-32768,32767).astype("<i2").tobytes())
    template=load_template("templates/04_tokyo_night.json")
    for name,fmt in (("01_screen.mp4","mp4"),("02_alpha.webm","webm"),("03_prores4444.mov","mov")):render_audio(audio,root/name,template,ExportOptions(1280,720,30,"PREVIEW","CPU",fmt))
    audio.unlink();checklist="""CAPCUT TEST CHECKLIST

[ ] MP4 import
[ ] MP4 Screen blend
[ ] WebM import
[ ] WebM transparency
[ ] MOV import
[ ] MOV transparency
[ ] audio
[ ] sync
[ ] color
[ ] glow edge
[ ] playback

Record CapCut version and issues below:
"""; (root/"CAPCUT_TEST_CHECKLIST.txt").write_text(checklist,encoding="utf-8");(root/"README_CAPCUT_TEST.md").write_text("""# CapCut compatibility test\n\nImport all three files and check:\n\n- Each file imports and plays normally with audio.\n- `01_screen.mp4` works over footage using Screen blend.\n- `02_alpha.webm` preserves transparency if the CapCut build supports VP9 alpha.\n- `03_prores4444.mov` preserves transparency.\n- Colors match, frame rate is stable, and duration matches.\n\nRecord CapCut version and any observed color, alpha, audio, or timing issue.\n""",encoding="utf-8");print(root.resolve())
if __name__=="__main__":main()
