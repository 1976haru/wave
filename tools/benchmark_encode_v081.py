from pathlib import Path
import sys,time,wave,json
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from template_system import load_template
from pipeline.exporter import ExportOptions,render_audio
root=Path('validation_results/v081_encode'); root.mkdir(parents=True,exist_ok=True); sr=8000; sec=3; audio=root/'source.wav'; t=np.arange(sr*sec)/sr; data=(np.sin(2*np.pi*220*t)*.4*32767).astype(np.int16); h=wave.open(str(audio),'wb'); h.setnchannels(1); h.setsampwidth(2); h.setframerate(sr); h.writeframes(data.tobytes()); h.close()
report={}
for label,name in {'Tokyo Neon':'18_tokyo_neon.json','Chill Ribbon':'23_chill_ribbon.json','Spectrum Ring':'38_spectrum_ring.json','Radial Wave':'40_radial_wave.json'}.items():
 out=root/(label.replace(' ','_')+'.webm'); start=time.perf_counter(); result=render_audio(audio,out,load_template(Path('templates')/name),ExportOptions(320,180,24,'PREVIEW','AUTO','webm'),logger=lambda *_:None); elapsed=time.perf_counter()-start; report[label]={'elapsed_seconds':elapsed,'realtime_ratio':sec/elapsed,'average_fps':result.get('average_fps'),'bottleneck':result.get('bottleneck'),'output':str(out)}
Path('validation_results/v081_encode_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report,indent=2))

