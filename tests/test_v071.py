import json
from pathlib import Path
import pytest
from PySide6.QtCore import QSettings
from mws_queue.queue_manager import JobSet,QueueManager
from mws_queue.sleep_prevention import SleepPrevention
from ui.locale import Translator,TRANSLATIONS

def make_set(tmp_path,index=0):
    source=tmp_path/f"{index}.wav";source.write_bytes(b"audio")
    return JobSet(name=f"set-{index}",tracks=[{"audio":str(source),"preset":"01_clean_bars","format":"webm"}],output_dir=str(tmp_path/f"out-{index}"))

def test_queue_max_five(tmp_path):
    manager=QueueManager(tmp_path/"queue.json")
    for index in range(5):manager.add(make_set(tmp_path,index))
    with pytest.raises(ValueError):manager.add(make_set(tmp_path,6))
    assert len(manager.sets)==5

def test_queue_persistence(tmp_path):
    path=tmp_path/"queue.json";manager=QueueManager(path);manager.add(make_set(tmp_path));restored=QueueManager(path)
    assert restored.sets[0].name=="set-0" and restored.sets[0].tracks[0]["audio"]

def test_queue_running_recovers_to_pending(tmp_path):
    path=tmp_path/"queue.json";manager=QueueManager(path);item=make_set(tmp_path);item.status="running";manager.add(item);restored=QueueManager(path)
    assert restored.sets[0].status=="pending"

def test_queue_reorder(tmp_path):
    manager=QueueManager(tmp_path/"queue.json")
    for index in range(3):manager.add(make_set(tmp_path,index))
    assert manager.move_down(0) and [item.name for item in manager.sets]==["set-1","set-0","set-2"]
    assert manager.move_up(1) and manager.sets[0].name=="set-0"

def test_queue_duplicate(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(make_set(tmp_path));clone=manager.duplicate(0)
    assert clone.id!=manager.sets[0].id and clone.status=="pending" and len(manager.sets)==2

def test_queue_remove(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(make_set(tmp_path));assert manager.remove(0).name=="set-0" and not manager.sets

def test_queue_preflight_missing_source(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(JobSet("bad",[{"audio":str(tmp_path/"missing.wav")}],output_dir=str(tmp_path/"out")))
    result=manager.preflight();assert not result[0]["ready"] and result[0]["errors"]

def test_queue_preflight_template(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(make_set(tmp_path))
    result=manager.preflight(lambda name: (_ for _ in ()).throw(ValueError("preset missing")))
    assert not result[0]["ready"]

def test_queue_run_all_sets(tmp_path):
    manager=QueueManager(tmp_path/"queue.json")
    for index in range(3):manager.add(make_set(tmp_path,index))
    result=manager.run(lambda track,job: {"output":"done"})
    assert result.success and result.sets_success==3 and all(item.status=="completed" for item in manager.sets)

def test_queue_continues_track_failure(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(JobSet("mixed",[{"audio":"ok"},{"audio":"bad"},{"audio":"ok2"}],output_dir=str(tmp_path)))
    def render(track,job):
        if track["audio"]=="bad":raise RuntimeError("decode")
        return {}
    result=manager.run(render)
    assert result.sets_failed==1 and result.tracks_success==2 and result.tracks_failed==1 and manager.sets[0].status=="failed"

def test_queue_continues_next_set_after_failure(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(JobSet("bad",[{"audio":"bad"}],output_dir=str(tmp_path)));manager.add(JobSet("good",[{"audio":"good"}],output_dir=str(tmp_path)))
    result=manager.run(lambda track,job: (_ for _ in ()).throw(RuntimeError("fail")) if track["audio"]=="bad" else {})
    assert result.sets_failed==1 and result.sets_success==1 and manager.sets[1].status=="completed"

def test_queue_skip_completed(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");item=make_set(tmp_path);item.status="completed";item.tracks[0]["status"]="completed";item.completed=1;manager.add(item);called=[];result=manager.run(lambda *args:called.append(1),skip_completed=True)
    assert result.tracks_success==0 and not called

def test_queue_cancel(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(JobSet("cancel",[{"audio":"a"},{"audio":"b"}],output_dir=str(tmp_path)))
    def render(*args):
        manager.request_cancel();return {}
    result=manager.run(render)
    assert not manager.running and result.tracks_success==1

def test_queue_progress_callback(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(make_set(tmp_path));events=[];manager.run(lambda *args:{},progress=lambda *args:events.append(args))
    assert events and events[-1][0]==1 and events[-1][2]==1

def test_job_set_snapshot_isolated(tmp_path):
    item=make_set(tmp_path);snapshot=item.snapshot();snapshot["tracks"][0]["audio"]="changed";assert item.tracks[0]["audio"]!="changed"

def test_job_set_progress(tmp_path):
    item=make_set(tmp_path);assert item.progress==0;item.completed=1;assert item.progress==1

def test_queue_result_failure_property(tmp_path):
    manager=QueueManager(tmp_path/"queue.json");manager.add(JobSet("bad",[{"audio":"x"}],output_dir=str(tmp_path)));result=manager.run(lambda *args: (_ for _ in ()).throw(RuntimeError("x")));assert not result.success

def test_sleep_guard_is_noop_off_windows():
    guard=SleepPrevention(True)
    with guard:pass
    assert not guard.active

def test_korean_is_default():
    translator=Translator();assert translator.language=="ko" and translator.tr("step1").startswith("1.")

def test_english_locale():
    translator=Translator("en");assert translator.tr("step1")=="1. Select Audio"

def test_locale_fallback():
    translator=Translator("xx");assert translator.language=="ko"

def test_locale_format():
    assert Translator().tr("queue_count",count=3).endswith("3 / 5")

def test_translation_keys_match():
    assert set(TRANSLATIONS["ko"])==set(TRANSLATIONS["en"])
