import json

from mws_queue.queue_manager import JobSet, QueueManager
from pipeline.batch import BatchRunner
from ui.main_window import MainWindow, TaskWorker


def make_manager(tmp_path, tracks=None):
    manager = QueueManager(tmp_path / "queue_state.json")
    manager.add(JobSet("test", tracks or [{"audio": "one.wav"}], output_dir=str(tmp_path)))
    return manager


def test_queue_manager_cancel_exists_and_delegates(tmp_path):
    manager = make_manager(tmp_path)

    manager.cancel()

    assert manager.cancel_requested is True
    assert manager.pause_requested is False


def test_task_worker_cancel_supports_queue_manager(tmp_path):
    manager = make_manager(tmp_path)
    worker = TaskWorker("queue", (manager, False))
    worker.runner = manager

    worker.cancel()

    assert manager.cancel_requested is True


def test_task_worker_cancel_preserves_batch_runner_behavior():
    runner = BatchRunner()
    worker = TaskWorker("render", None)
    worker.runner = runner

    worker.cancel()

    assert runner.cancelled is True


def test_task_worker_cancel_falls_back_to_request_cancel():
    class RequestOnlyRunner:
        def __init__(self):
            self.calls = 0

        def request_cancel(self):
            self.calls += 1

    runner = RequestOnlyRunner()
    worker = TaskWorker("queue", None)
    worker.runner = runner

    worker.cancel()

    assert runner.calls == 1


def test_repeated_cancel_is_safe(tmp_path):
    manager = make_manager(tmp_path)
    worker = TaskWorker("queue", (manager, False))
    worker.runner = manager

    worker.cancel()
    worker.cancel()
    worker.cancel()

    assert manager.cancel_requested is True


def test_stop_during_queue_run_marks_cancelled_and_retains_job(tmp_path):
    manager = make_manager(tmp_path, [{"audio": "one.wav"}, {"audio": "two.wav"}])
    worker = TaskWorker("queue", (manager, False))
    worker.runner = manager

    def render_and_stop(*_):
        worker.cancel()
        return {}

    result = manager.run(render_and_stop)

    assert manager.cancel_requested is True
    assert manager.running is False
    assert result.completed_removed == 0
    assert len(manager.sets) == 1
    assert manager.sets[0].status == "cancelled"


def test_restart_after_cancel_recovers_queue_without_crash(tmp_path):
    path = tmp_path / "queue_state.json"
    manager = QueueManager(path)
    manager.add(JobSet("cancelled", [{"audio": "one.wav"}, {"audio": "two.wav"}], output_dir=str(tmp_path)))

    manager.run(lambda *_: (manager.cancel(), {})[1])
    restarted = QueueManager(path)

    assert len(restarted.sets) == 1
    assert restarted.sets[0].status == "cancelled"


def test_restart_after_completion_has_empty_queue(tmp_path):
    path = tmp_path / "queue_state.json"
    manager = QueueManager(path)
    manager.add(JobSet("completed", [{"audio": "one.wav"}], output_dir=str(tmp_path)))

    result = manager.run(lambda *_: {})
    restarted = QueueManager(path)

    assert result.completed_removed == 1
    assert restarted.sets == []
    assert json.loads(path.read_text(encoding="utf-8"))["sets"] == []


def make_window(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    monkeypatch.setenv("MWS_SMOKE_TEST", "1")
    monkeypatch.chdir(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    return app, window


def test_close_event_idle_is_safe(monkeypatch, tmp_path):
    app, window = make_window(monkeypatch, tmp_path)

    assert window.close() is True
    app.processEvents()


def test_close_event_queue_running_is_safe(monkeypatch, tmp_path):
    app, window = make_window(monkeypatch, tmp_path)
    manager = make_manager(tmp_path / "running")
    manager.running = True
    window.worker = TaskWorker("queue", (manager, False))
    window.worker.runner = manager

    assert window.close() is True
    app.processEvents()

    assert manager.cancel_requested is True


def test_close_event_after_queue_completion_is_safe(monkeypatch, tmp_path):
    app, window = make_window(monkeypatch, tmp_path)
    manager = make_manager(tmp_path / "completed")
    manager.run(lambda *_: {})
    window.worker = TaskWorker("queue", (manager, False))
    window.worker.runner = manager

    assert window.close() is True
    app.processEvents()

    assert manager.cancel_requested is True


def test_stop_button_cancels_running_queue_without_closing_app(monkeypatch, tmp_path):
    app, window = make_window(monkeypatch, tmp_path)
    manager = make_manager(tmp_path / "stop-button")
    manager.running = True
    window.worker = TaskWorker("queue", (manager, False))
    window.worker.runner = manager
    window.show()

    window.stop_button.click()
    app.processEvents()

    assert manager.cancel_requested is True
    assert window.isVisible() is True
    window.close()
