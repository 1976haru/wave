"""Report runtime readiness without changing the system."""
from __future__ import annotations
import argparse,importlib.util,json,platform,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def parse_encoders(text):
    result=set()
    for line in text.splitlines():
        parts=line.split()
        if len(parts)>=2 and len(parts[0])==6:result.add(parts[1])
    return result
def _item(status,detail):return {"status":status,"detail":detail}
def check_system():
    checks={};version=sys.version_info;recommended=(3,12)<=version[:2]<=(3,13);checks["python"]=_item("PASS" if recommended else "WARNING",f"{platform.python_version()} (recommended 3.12 or 3.13)")
    for command in ("ffmpeg","ffprobe"):
        path=shutil.which(command);checks[command]=_item("PASS" if path else "FAIL",path or "not found on PATH")
    for module,label,required in (("PySide6","PySide6",True),("numpy","NumPy",True),("cv2","OpenCV",True),("av","PyAV",False),("moderngl","ModernGL",False)):
        found=importlib.util.find_spec(module) is not None;checks[label]=_item("PASS" if found else ("FAIL" if required else "WARNING"),"installed" if found else "not installed")
    checks["gpu_context"]=_item("WARNING","not tested")
    if importlib.util.find_spec("moderngl"):
        try:
            import moderngl
            context=moderngl.create_standalone_context(require=330);checks["gpu_context"]=_item("PASS",context.info.get("GL_RENDERER","OpenGL 3.3 context"));context.release()
        except Exception as exc:checks["gpu_context"]=_item("WARNING",str(exc))
    encoders=set()
    if shutil.which("ffmpeg"):
        process=subprocess.run([shutil.which("ffmpeg"),"-hide_banner","-encoders"],capture_output=True,text=True);encoders=parse_encoders(process.stdout+process.stderr)
    for label,names in (("H.264",("libx264","h264_nvenc","h264_amf")),("VP9",("libvpx-vp9",)),("ProRes",("prores_ks",))):
        available=sorted(set(names)&encoders);checks[label]=_item("PASS" if available else "FAIL",", ".join(available) or "encoder unavailable")
    return checks
def format_report(checks):return "\n".join(f"{item['status']:7} {name:14} {item['detail']}" for name,item in checks.items())
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--json",action="store_true");args=parser.parse_args();result=check_system();print(json.dumps(result,indent=2) if args.json else format_report(result))
