from __future__ import annotations

import copy

import cv2
import numpy as np

from template_system import load_template
from visualizers.families.soft_round_led import SoftRoundLEDRenderer, resolve_profile
from visualizers.local_background import (
    adaptation_from_metrics, analyze_local_background, derive_underlay_color,
    smooth_adaptation, waveform_roi,
)
from visualizers.schema import validate_waveform


def _metrics(image: np.ndarray):
    return analyze_local_background(image, (0, 0, image.shape[1], image.shape[0]))


def test_dark_mid_bright_and_white_roi_progression():
    dark = adaptation_from_metrics(_metrics(np.full((80, 240, 3), 8, np.uint8)))
    mid = adaptation_from_metrics(_metrics(np.full((80, 240, 3), 128, np.uint8)))
    bright = adaptation_from_metrics(_metrics(np.full((80, 240, 3), 225, np.uint8)))
    white = adaptation_from_metrics(_metrics(np.full((80, 240, 3), 255, np.uint8)))
    assert dark["underlay_alpha"] < mid["underlay_alpha"] < bright["underlay_alpha"] <= white["underlay_alpha"] <= .38
    assert dark["glow_multiplier"] > bright["glow_multiplier"] >= .5


def test_high_texture_increases_difficulty_and_contrast_support():
    flat = np.full((80, 240, 3), 150, np.uint8)
    checker = (((np.indices((80, 240)).sum(axis=0) // 3) % 2) * 180 + 60).astype(np.uint8)
    textured = np.dstack((checker, checker, checker))
    flat_adapt = adaptation_from_metrics(_metrics(flat)); texture_adapt = adaptation_from_metrics(_metrics(textured))
    assert _metrics(textured).texture_density > _metrics(flat).texture_density
    assert texture_adapt["underlay_alpha"] > flat_adapt["underlay_alpha"]
    assert texture_adapt["glow_multiplier"] < flat_adapt["glow_multiplier"]


def test_temporal_ema_damps_abrupt_change():
    low = adaptation_from_metrics(_metrics(np.zeros((40, 120, 3), np.uint8)))
    high = adaptation_from_metrics(_metrics(np.full((40, 120, 3), 255, np.uint8)))
    smoothed = smooth_adaptation(low, high, .16)
    assert low["underlay_alpha"] < smoothed["underlay_alpha"] < high["underlay_alpha"]
    assert abs(smoothed["underlay_alpha"] - low["underlay_alpha"]) < abs(high["underlay_alpha"] - low["underlay_alpha"])


def test_custom_underlay_is_palette_derived_and_not_black():
    color = derive_underlay_color([[0, "#FFCC88"], [1, "#FF55AA"]], "CUSTOM")
    assert color != (0, 0, 0) and max(color) <= 82 and min(color) >= 18
    assert color[0] > color[2]


def test_old_waveform_defaults_local_adapt_true():
    old = {"format":"MusicWaveStudioWaveform", "format_version":1, "name":"Old", "renderer_family":"soft_round_led",
           "theme":"NEON", "intensity":"STANDARD", "width":"STANDARD", "position":"LEFT",
           "color_mode":"THEME", "colors":[], "auto_adapt":True, "advanced":{}}
    clean, warnings = validate_waveform(old, {"soft_round_led"})
    assert clean["local_adapt"] is True and not warnings


def test_geometry_is_identical_with_local_adaptation():
    template = load_template("templates/00_universal_soft_round_led.json")
    profile_before = resolve_profile(template, 960, 160, {"auto_gain": 1.0})
    state = {"values": np.linspace(.1, .9, 64, dtype=np.float32), "auto_gain": 1.0,
             "background_frame": np.full((160, 960, 3), 245, np.uint8)}
    renderer = SoftRoundLEDRenderer(); renderer.render_rgba(960, 160, state, copy.deepcopy(template))
    profile_after = resolve_profile(template, 960, 160, state)
    for key in ("bands", "active_width", "dot_diameter", "horizontal_gap", "vertical_gap", "amplitude_gain", "attack", "release"):
        assert profile_before[key] == profile_after[key]
    assert waveform_roi(profile_before, 960, 160) == waveform_roi(profile_after, 960, 160)


def test_renderer_bright_roi_has_more_visible_core_without_outline_panel():
    template = load_template("templates/00_universal_soft_round_led.json")
    values = np.full(64, .62, np.float32)
    dark_state = {"values": values, "auto_gain": 1.0, "background_frame": np.full((160, 960, 3), 10, np.uint8)}
    bright_state = {"values": values, "auto_gain": 1.0, "background_frame": np.full((160, 960, 3), 245, np.uint8)}
    dark = SoftRoundLEDRenderer().render_rgba(960, 160, dark_state, copy.deepcopy(template))
    bright = SoftRoundLEDRenderer().render_rgba(960, 160, bright_state, copy.deepcopy(template))
    # Bright-background mode intentionally darkens/saturates the core instead of
    # whitening it, so its contrast distance from white must increase.
    dark_contrast = np.mean(255 - dark[..., :3][dark[..., 3] > 20])
    bright_contrast = np.mean(255 - bright[..., :3][bright[..., 3] > 20])
    assert bright_contrast > dark_contrast
    # Adaptation stays dot-local: no rectangular/backplate alpha area appears.
    assert np.mean(bright[..., 3] > 0) < .20
