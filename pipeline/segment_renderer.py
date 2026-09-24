from __future__ import annotations
import subprocess
from pathlib import Path
from pipeline.segment_resume import recover_manifest, checkpoint, plan_segments, atomic_write_json
from pipeline.exporter import render_audio
from core.ffmpeg import resolve_ffmpeg

def _hidden(ffmpeg):
    if __import__('os').name != 'nt': return {'stdout':subprocess.PIPE,'stderr':subprocess.PIPE}
    si=subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow=0
    return {'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0),'startupinfo':si}

def render_segmented_track(source,target,template,options,manifest_path,segment_root,progress_detail=None,cancel=None):
    source=Path(source); target=Path(target); root=Path(segment_root); root.mkdir(parents=True,exist_ok=True)
    manifest=recover_manifest(manifest_path,{"format":options.format,"resolution":f"{options.width}x{options.height}","fps":options.fps,"quality":options.quality,"renderer":options.renderer,"ffmpeg_path":options.ffmpeg_path,"width":options.width,"height":options.height,"canvas_mode":options.canvas_mode,"preset_id":template.get("name",""),"template":template},root)
    if manifest is None or manifest.get("incompatible"):
        raise RuntimeError("파형 또는 출력 설정이 변경되어 현재 곡은 처음부터 다시 만듭니다.")
    segments=plan_segments(manifest["track_duration"],options.fps)
    done=set(manifest.get("completed_segments",[])); total=len(segments)
    for seg in segments:
        if seg.index in done: continue
        seg_path=root/f"segment_{seg.index:03d}{target.suffix}"
        tmp=seg_path.with_name(seg_path.stem+'.tmp'+seg_path.suffix)
        if tmp.exists(): tmp.unlink()
        def detail(event, s=seg):
            if progress_detail:
                local=float(event.get('percent',0.0)); overall=((s.start_frame + local/100.0*s.frame_count) / max(segments[-1].end_frame+1,1))*100.0
                progress_detail({**event,'percent':overall,'segment_index':s.index,'resume_seconds':s.start_frame/options.fps})
        render_audio(source,tmp,template,options,progress_detail=detail,cancel=cancel,start_frame=seg.start_frame,end_frame=seg.end_frame)
        tmp.replace(seg_path)
        checkpoint(manifest_path,manifest,seg.index,root)
        manifest=recover_manifest(manifest_path,{"format":options.format,"resolution":f"{options.width}x{options.height}","fps":options.fps,"quality":options.quality,"renderer":options.renderer,"ffmpeg_path":options.ffmpeg_path,"width":options.width,"height":options.height,"canvas_mode":options.canvas_mode,"preset_id":template.get("name",""),"template":template},root) or manifest
    if len(manifest.get('completed_segments',[])) < total: raise RuntimeError('segment checkpoint incomplete')
    if target.suffix.lower()=='.webm':
        ffmpeg=resolve_ffmpeg(options.ffmpeg_path)
        if not ffmpeg: raise RuntimeError('FFmpeg is required for segment concat')
        listfile=root/'concat.txt'; listfile.write_text(''.join(f"file '{(root/f"segment_{i:03d}{target.suffix}").resolve().as_posix().replace("'","'\\''")}\n" for i in range(total)),encoding='utf-8')
        tmpout=target.with_name(target.stem+'.tmp'+target.suffix)
        cmd=[ffmpeg,'-y','-v','error','-f','concat','-safe','0','-i',str(listfile),'-c','copy',str(tmpout)]
        proc=subprocess.run(cmd,**_hidden(ffmpeg),check=False)
        if proc.returncode: raise RuntimeError('segment concat failed')
        tmpout.replace(target)
    else:
        raise RuntimeError('segment resume currently requires WebM output')
    manifest['status']='completed'; manifest['next_segment']=total; atomic_write_json(manifest_path,manifest)
    return {'output':str(target),'resume_seconds':0.0,'completed_segments':list(range(total)),'segment_count':total}