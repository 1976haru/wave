import numpy as np

from visualizers.registry import registry
from visualizers.families.soft_round_led import load_profiles, resolve_profile


def test_registry_exposes_only_completed_family():
    assert registry.ids() == ("soft_round_led", "tokyo_signature")
    family = registry.get("soft_round_led")
    assert family.display_name == "Soft Round LED"
    assert "theme" in family.supported_parameters


def test_seven_production_themes_and_modifiers_load():
    _base, modifiers, themes = load_profiles()
    assert set(themes) == {"NEON", "WARM", "ELEGANT", "SOFT", "ENERGETIC", "MONO", "CUSTOM"}
    assert modifiers["width"] == {"COMPACT": {"active_width": 360}, "STANDARD": {"active_width": 460}, "WIDE": {"active_width": 560}}


def test_family_renders_round_dot_rgba_without_baseline():
    template = {"renderer_family": "soft_round_led", "universal_visualizer": {"theme": "NEON", "intensity": "STANDARD", "width": "STANDARD", "position": "LEFT", "color_mode": "THEME", "colors": [], "auto_adapt": True, "advanced": {}}}
    state = {"values": np.linspace(.05, .95, 64, dtype=np.float32), "auto_gain": 1.0}
    frame = registry.create("soft_round_led").render_rgba(960, 160, state, template)
    assert frame.shape == (160, 960, 4) and frame[..., 3].max() > 0
    assert not np.any(frame[145:, :, 3])


def test_theme_intensity_width_position_are_independent():
    template = {"universal_visualizer": {"theme": "WARM", "intensity": "DYNAMIC", "width": "WIDE", "position": "RIGHT", "auto_adapt": False, "advanced": {}}}
    profile = resolve_profile(template, 960, 160)
    assert profile["active_width"] == 560
    assert profile["x_position"] == 330
    assert profile["amplitude_gain"] > .93
