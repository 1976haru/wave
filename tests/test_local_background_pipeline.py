from __future__ import annotations

import copy
from pathlib import Path

import cv2
import numpy as np

from template_system import load_template
from visualizers.background_source import LocalBackgroundSource, source_from_template


TEST_DIR = Path("validation_results/v0841_local_adapt_test")


def _path(name: str) -> Path:
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    return TEST_DIR / name


def test_static_reference_is_cropped_and_scaled():
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[850:1010, 70:1030] = (210, 220, 230)
    path = _path("reference.png")
    assert cv2.imwrite(str(path), image)
    source = LocalBackgroundSource(path)
    frame = source.frame(0, 960, 160)
    assert source.available and frame.shape == (160, 960, 3)
    assert float(np.mean(frame)) > 205


def test_template_source_respects_local_adapt_toggle():
    path = _path("reference_toggle.png")
    assert cv2.imwrite(str(path), np.full((1080, 1920, 3), 180, np.uint8))
    template = load_template("templates/00_universal_soft_round_led.json")
    template["_local_background_source"] = str(path)
    assert source_from_template(template) is not None
    disabled = copy.deepcopy(template); disabled["universal_visualizer"]["local_adapt"] = False
    assert source_from_template(disabled) is None


def test_source_uses_overlay_roi_not_full_screen():
    image = np.full((1080, 1920, 3), 12, np.uint8)
    image[850:1010, 70:1030] = 244
    path = _path("bright_lower_third.png")
    assert cv2.imwrite(str(path), image)
    template = load_template("templates/00_universal_soft_round_led.json")
    template["_local_background_source"] = str(path)
    frame = source_from_template(template).frame(0, 960, 160)
    assert float(np.median(frame)) > 235
