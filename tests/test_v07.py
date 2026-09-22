import json
from pathlib import Path
import numpy as np,pytest
from PySide6.QtCore import QSettings
from audio import analyzer
from audio.analyzer import ANALYSIS_VERSION,AnalysisSettings,_edges,_window,analyze_pcm,cache_key
from audio.experimental import OptionalAnalyzerUnavailable,librosa_available
from core.errors import user_message
from core.ffmpeg import resolve_ffmpeg
from core.settings import AppSettings
from core.storage import disk_space,disk_warning
from integration.hub_adapter import HubAdapter
from integration.job_contract import validate_job
from playlist.model import PlaylistProject,PlaylistTrack
from render_job import resolve_template,run_job
from template_system import DEFAULT_TEMPLATE
from template_system.thumbnails import get_thumbnail,template_hash

@pytest.mark.parametrize("name",["hann","hamming","blackman"])
def test_fft_windows(name):assert _window(name,64).shape==(64,)
def test_bad_fft_window(): 
    with pytest.raises(ValueError):_window("triangle",64)
def test_perceptual_edges_monotonic():assert np.all(np.diff(_edges(40,16000,64,"PERCEPTUAL"))>0)
def test_log_and_perceptual_differ():assert not np.allclose(_edges(40,16000,16,"LOG"),_edges(40,16000,16,"PERCEPTUAL"))
def test_detailed_frequency_features():
    x=np.sin(2*np.pi*50*np.arange(16000)/16000);features=analyze_pcm(x,16000,fps=20,bands=16,fft_size=512,analyzer_backend="NUMPY");assert {"sub","bass_detail","low_mid","mid_detail","upper_mid","high_detail","air"}<=features.keys()
def test_scipy_backend_when_available():
    features=analyze_pcm(np.zeros(4000),8000,fps=20,bands=8,fft_size=256,analyzer_backend="SCIPY");assert str(features["analysis_backend"][0]) in {"SCIPY","NUMPY"}
def test_cache_key_changes_window(tmp_path):
    audio=tmp_path/"x";audio.write_bytes(b"audio");assert cache_key(audio,AnalysisSettings(fft_window="hann"))!=cache_key(audio,AnalysisSettings(fft_window="blackman"))
def test_cache_key_changes_mapping(tmp_path):
    audio=tmp_path/"x";audio.write_bytes(b"audio");assert cache_key(audio,AnalysisSettings(spectrum_mapping="LOG"))!=cache_key(audio,AnalysisSettings(spectrum_mapping="PERCEPTUAL"))
def test_analysis_version_two():assert ANALYSIS_VERSION=="2"
def test_librosa_optional_contract():
    if not librosa_available():
        with pytest.raises(OptionalAnalyzerUnavailable):
            from audio.experimental import analyze_librosa
            analyze_librosa(np.zeros(10),8000)
def test_playlist_add_deduplicates(tmp_path):
    p=tmp_path/"a.wav";p.write_bytes(b"x");project=PlaylistProject();project.add_files([p,p]);assert len(project.tracks)==1
def test_playlist_reorder(tmp_path):
    paths=[tmp_path/f"{x}.wav" for x in "abc"];[p.write_bytes(b"x") for p in paths];project=PlaylistProject();project.add_files(paths);ids=[x.id for x in project.tracks][::-1];project.reorder(ids);assert [x.id for x in project.tracks]==ids
def test_playlist_move_bounds(tmp_path):
    p=PlaylistProject([PlaylistTrack(str(tmp_path/"a"))]);assert not p.move_up(0)
def test_per_track_preset_and_export(tmp_path):
    track=PlaylistTrack(str(tmp_path/"x"),preset="Tokyo Night",output_format="mov",export_override={"fps":60});assert track.preset=="Tokyo Night" and track.output_format=="mov" and track.export_override["fps"]==60
def test_playlist_save_load_missing(tmp_path):
    project=PlaylistProject([PlaylistTrack(str(tmp_path/"missing.wav"))]);path=tmp_path/"p.mwsplaylist.json";project.save(path);loaded=PlaylistProject.load(path);assert loaded.tracks[0].missing
def test_apply_preset_all(tmp_path):
    project=PlaylistProject([PlaylistTrack(str(tmp_path/"a")),PlaylistTrack(str(tmp_path/"b"))]);project.apply_preset_to_all("Thin Line");assert all(x.preset=="Thin Line" for x in project.tracks)
def test_retry_failed():
    project=PlaylistProject([PlaylistTrack("x",status="failed"),PlaylistTrack("y",status="completed")]);project.retry_failed();assert [x.status for x in project.tracks]==["pending","completed"]
def test_job_normalizes_string_track(tmp_path):
    job=validate_job({"tracks":[str(tmp_path/"a.wav")],"output_dir":str(tmp_path)});assert job["tracks"][0]["format"]=="webm"
def test_job_rejects_bad_format(tmp_path):
    with pytest.raises(ValueError):validate_job({"tracks":["x"],"output_dir":str(tmp_path),"format":"avi"})
def test_headless_partial_failure_result(tmp_path):
    audio=tmp_path/"a.wav";audio.write_bytes(b"x");job={"tracks":[{"audio":str(audio),"format":"mp4"},{"audio":str(tmp_path/"missing"),"format":"mp4"}],"output_dir":str(tmp_path)}
    result=run_job(job,render_fn=lambda source,target,template,options:{"ok":True});assert result["success"]==1 and result["failed"]==1 and (tmp_path/"result.json").exists()
def test_hub_adapter_command(tmp_path):assert "--headless" in HubAdapter("MusicWaveStudio.exe").command(tmp_path/"job.json")
def test_resolve_named_template():assert resolve_template("Clean Bars")["name"].endswith("Clean Bars")
def test_settings_roundtrip(tmp_path):
    native=QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat);settings=AppSettings(native);settings.set("quality","QUALITY");native.sync();assert settings.get("quality")=="QUALITY"
def test_settings_reject_unknown(tmp_path):
    settings=AppSettings(QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat))
    with pytest.raises(KeyError):settings.set("unknown",1)
def test_ffmpeg_custom_path(tmp_path):
    exe=tmp_path/"ffmpeg.exe";exe.write_bytes(b"x");assert resolve_ffmpeg(exe)==str(exe)
def test_disk_space_contract(tmp_path):assert disk_space(tmp_path)["free"]>0 and "warning" in disk_warning(tmp_path,0)
def test_error_messages_are_actionable():assert "FFmpeg" in user_message(RuntimeError("ffmpeg missing"))
def test_template_hash_stable():assert template_hash(DEFAULT_TEMPLATE)==template_hash(dict(DEFAULT_TEMPLATE))
def test_thumbnail_cache(tmp_path):
    first,hit1=get_thumbnail(dict(DEFAULT_TEMPLATE,glow=False),tmp_path);second,hit2=get_thumbnail(dict(DEFAULT_TEMPLATE,glow=False),tmp_path);assert first==second and not hit1 and hit2
