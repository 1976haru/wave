import json
from pathlib import Path
from pipeline.segment_resume import plan_segments, settings_hash, atomic_write_json, manifest_for, checkpoint, recover_manifest, ensure_manifest

def test_frame_based_segment_planning():
    parts=plan_segments(25,30)
    assert [(p.start_frame,p.end_frame) for p in parts]==[(0,299),(300,599),(600,749)]

def test_settings_hash_is_stable_and_sensitive():
    assert settings_hash({'a':1,'b':'x'})==settings_hash({'b':'x','a':1})
    assert settings_hash({'a':1})!=settings_hash({'a':2})

def test_atomic_manifest_and_checkpoint(tmp_path):
    root=tmp_path/'track'; manifest_path=root/'manifest.json'; segs=plan_segments(21,30)
    manifest=manifest_for('song.wav',21,30,{'format':'webm'},segs)
    atomic_write_json(manifest_path,manifest)
    (root/'segment_000.webm').write_bytes(bytes.fromhex('1a45dfa3')+b'ok')
    assert checkpoint(manifest_path,manifest,0,root)
    saved=json.loads(manifest_path.read_text(encoding='utf-8'))
    assert saved['completed_segments']==[0] and saved['next_segment']==1

def test_incomplete_segment_is_not_recovered(tmp_path):
    root=tmp_path/'track'; manifest_path=root/'manifest.json'; segs=plan_segments(21,30)
    settings={'format':'webm'}; manifest=manifest_for('song.wav',21,30,settings,segs); manifest['completed_segments']=[0,1]
    atomic_write_json(manifest_path,manifest)
    (root/'segment_000.webm').write_bytes(bytes.fromhex('1a45dfa3')+b'ok'); (root/'segment_001.webm.tmp').write_bytes(b'partial')
    recovered=recover_manifest(manifest_path,settings,root)
    assert recovered['completed_segments']==[0]

def test_incompatible_settings_require_restart(tmp_path):
    root,path,manifest,_=ensure_manifest(tmp_path,'song.wav',25,30,{'format':'webm','preset_id':'a'})
    result=recover_manifest(path,{'format':'webm','preset_id':'b'},root)
    assert result['incompatible'] is True

def test_resume_progress_is_checkpoint_based(tmp_path):
    root,path,manifest,segs=ensure_manifest(tmp_path,'song.wav',180,30,{'format':'webm','preset_id':'a'})
    for i in range(4):
        (root/f'segment_{i:03d}.webm').write_bytes(bytes.fromhex('1a45dfa3')+b'ok')
        assert checkpoint(path,manifest,i,root)
        manifest=json.loads(path.read_text(encoding='utf-8'))
    recovered=recover_manifest(path,{'format':'webm','preset_id':'a'},root)
    assert recovered['next_segment']==4
    assert recovered['next_segment']*10==40


