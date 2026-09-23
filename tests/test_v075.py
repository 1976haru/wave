import os,time
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import cv2,numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop,QTimer
import pytest
from ui.main_window import MainWindow,ReferenceAnalysisWorker
from tools.check_locale import check_locale

@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.app_settings.set("first_run_done",True);yield w;w.close()

def test_locale_integrity(): assert check_locale()==[]

def test_korean_folder_label(window):
    assert window.translator.tr("add_folder") != "??" and "\ufffd" not in window.translator.tr("add_folder")

def test_reference_worker_success(tmp_path):
    image=np.zeros((120,240,3),np.uint8);image[:,40:80]=(0,255,0);path=tmp_path/"ref.png";cv2.imwrite(str(path),image);worker=ReferenceAnalysisWorker([str(path)]);results=[];worker.result_ready.connect(results.append);worker.run();assert results and "color" in results[0]

def test_reference_worker_failure_cleanup():
    worker=ReferenceAnalysisWorker(["missing.png"]);errors=[];finished=[];worker.failed.connect(errors.append);worker.finished.connect(lambda:finished.append(True));worker.run();assert errors and finished

def test_reference_worker_cancel():
    worker=ReferenceAnalysisWorker(["missing.png"]);cancelled=[];worker.cancelled.connect(lambda:cancelled.append(True));worker.cancel();worker.run();assert cancelled

def test_reference_analysis_does_not_disable_window(window,tmp_path,monkeypatch):
    assert window.isEnabled() and window.reference_analyze_button.isEnabled()
    assert window.reference_worker is None

def test_reference_double_click_guard(window,tmp_path,monkeypatch):
    assert window.reference_worker is None
    assert window.reference_analyze_button.isEnabled()

def test_transactional_reference_failure_keeps_template(window):
    before=dict(window.template);window.reference_analysis_failed("bad");assert window.template==before and window.reference_analyze_button.isEnabled()
