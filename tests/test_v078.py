import json
from pathlib import Path
from PySide6.QtWidgets import QApplication
import pytest

@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])
from ui.main_window import MainWindow
from template_system import list_templates, load_template


def test_builtin_gallery_has_at_least_30_presets():
    assert len(list_templates("templates")) >= 30


def test_builtin_preset_metadata_and_unique_ids():
    entries = list_templates("templates")
    ids = []
    for path, data in entries:
        ids.append(data.get("id", path.stem))
        assert data.get("name_en") or data.get("name")
        assert data.get("renderer") in {"bars", "line", "dot", "ribbon", "ring", "radial", "dot_matrix", "twin_dot_matrix", "dot_line_hybrid", "echo_dots", "stereo_signature"}
        assert data.get("category", "legacy")
    assert len(ids) == len(set(ids))


def test_builtin_presets_validate_json_utf8():
    for path in Path("templates").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "??" not in json.dumps(data, ensure_ascii=False)


def test_gallery_recommended_and_all_filters(qapp):
    window = MainWindow()
    assert window.template_filter.currentText()
    assert window.template_list.count() == 12
    window.template_filter.setCurrentText("전체 스타일")
    assert window.template_list.count() >= 30
    window.close()


def test_gallery_category_filter(qapp):
    window = MainWindow()
    window.template_filter.setCurrentText("Modern")
    assert window.template_list.count() >= 5
    window.close()



