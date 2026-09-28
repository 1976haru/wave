import json

import pytest

from mws_queue.queue_manager import JobSet, QueueManager


def job(name, status="pending", tracks=None):
    return JobSet(name, tracks or [{"audio": f"{name}.wav"}], output_dir="output", status=status)


def test_load_prunes_persisted_completed_sets_and_saves(tmp_path):
    path = tmp_path / "queue_state.json"
    path.write_text(json.dumps({"version": 1, "sets": [job(f"done-{i}", "completed").snapshot() for i in range(5)]}), encoding="utf-8")

    manager = QueueManager(path)

    assert manager.sets == []
    assert json.loads(path.read_text(encoding="utf-8"))["sets"] == []


def test_add_prunes_completed_before_capacity_check(tmp_path):
    manager = QueueManager(tmp_path / "queue_state.json")
    manager.sets = [job(f"pending-{i}") for i in range(4)] + [job("old", "completed")]

    manager.add(job("new"))

    assert len(manager.sets) == 5
    assert all(item.status == "pending" for item in manager.sets)


def test_five_pending_sets_still_enforce_limit(tmp_path):
    manager = QueueManager(tmp_path / "queue_state.json")
    for index in range(5):
        manager.add(job(f"pending-{index}"))

    with pytest.raises(ValueError, match="5"):
        manager.add(job("sixth"))

    assert len(manager.sets) == 5


def test_successful_set_is_removed_after_run_and_state_is_saved(tmp_path):
    path = tmp_path / "queue_state.json"
    manager = QueueManager(path)
    manager.add(job("success"))

    result = manager.run(lambda *_: {"output": "done"})

    assert result.sets_total == result.sets_success == result.completed_removed == 1
    assert result.tracks_success == 1
    assert manager.sets == []
    assert json.loads(path.read_text(encoding="utf-8"))["sets"] == []


def test_successful_sets_removed_but_failed_set_retained(tmp_path):
    manager = QueueManager(tmp_path / "queue_state.json")
    manager.add(job("success-1"))
    manager.add(job("failure", tracks=[{"audio": "bad.wav"}]))
    manager.add(job("success-2"))

    result = manager.run(lambda track, *_: (_ for _ in ()).throw(RuntimeError("render failed")) if track["audio"] == "bad.wav" else {})

    assert result.sets_success == 2 and result.sets_failed == 1
    assert result.completed_removed == 2
    assert len(manager.sets) == 1 and manager.sets[0].name == "failure"
    assert manager.sets[0].status == "failed"


def test_cancelled_job_is_retained(tmp_path):
    manager = QueueManager(tmp_path / "queue_state.json")
    manager.add(job("cancelled", tracks=[{"audio": "one.wav"}, {"audio": "two.wav"}]))

    def cancel_during_render(*_):
        manager.request_cancel()
        return {}

    result = manager.run(cancel_during_render)

    assert result.completed_removed == 0
    assert len(manager.sets) == 1 and manager.sets[0].status == "cancelled"


def test_seven_sequential_jobs_each_release_slot(tmp_path):
    manager = QueueManager(tmp_path / "queue_state.json")

    for index in range(7):
        manager.add(job(f"sequential-{index}"))
        result = manager.run(lambda *_: {})
        assert result.sets_total == result.sets_success == 1
        assert manager.sets == []


def test_queue_ui_refresh_removes_completed_card_and_disables_empty_start(tmp_path):
    from ui.queue_panel import QueuePanel
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    manager = QueueManager(tmp_path / "queue_state.json")
    manager.add(job("success"))
    panel = QueuePanel(manager)
    manager.run(lambda *_: {})
    panel.refresh()

    assert panel.summary.text().endswith("0 / 5")
    assert panel.cards.count() == 0
    assert not panel.start_button.isEnabled()
    panel.close()


def test_failed_set_remains_available_for_retry_in_queue_ui(tmp_path):
    from ui.queue_panel import QueuePanel
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    manager = QueueManager(tmp_path / "queue_state.json")
    manager.add(job("failed"))
    manager.run(lambda *_: (_ for _ in ()).throw(RuntimeError("render failed")))
    panel = QueuePanel(manager)
    panel.refresh()

    assert len(manager.sets) == 1 and manager.sets[0].status == "failed"
    assert panel.cards.count() == 1
    assert panel.start_button.isEnabled()
    panel.close()


def test_failed_set_can_be_retried_to_success(tmp_path):
    manager = QueueManager(tmp_path / "queue_state.json")
    manager.add(job("retry", tracks=[{"audio": "ok.wav"}, {"audio": "retry.wav"}]))
    manager.run(lambda track, *_: (_ for _ in ()).throw(RuntimeError("temporary error")) if track["audio"] == "retry.wav" else {})

    result = manager.run(lambda *_: {})

    assert result.sets_success == 1 and result.sets_failed == 0
    assert result.tracks_success == 2 and manager.sets == []


def test_set_render_still_creates_video_and_timeline(tmp_path):
    import wave
    import numpy as np
    from pipeline.exporter import ExportOptions
    from pipeline.set_renderer import render_set
    from template_system import load_template

    files = []
    samples = (np.sin(2 * np.pi * 220 * np.arange(4000) / 8000) * 12000).astype("<i2")
    for index in range(2):
        source = tmp_path / f"set-track-{index}.wav"
        with wave.open(str(source), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(samples.tobytes())
        files.append(source)
    template = load_template("templates/01_clean_bars.json")
    options = ExportOptions(width=128, height=72, fps=4, quality="PREVIEW", renderer="CPU", format="mp4", include_audio=False)
    target = tmp_path / "set-render.mp4"
    timeline = tmp_path / "set-timeline.json"

    result = render_set(files, target, template, options, timeline_path=timeline)

    assert result["tracks"] == 2 and result["frames"] >= 1
    assert target.exists() and target.stat().st_size > 0
    assert timeline.exists()
