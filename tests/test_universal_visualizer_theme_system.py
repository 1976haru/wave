import json
from pathlib import Path

import numpy as np

from tools.visualizer_prototypes.soft_round_led_engine import (
    auto_adapt, load_universal_themes, resolve_universal_profile,
)


ROOT = Path(__file__).resolve().parents[1]
THEMES = ROOT / "research/visualizer_candidates/universal_themes"


def test_seven_generic_themes_load_in_product_order():
    themes = load_universal_themes()
    assert list(themes) == ["NEON", "WARM", "ELEGANT", "SOFT", "ENERGETIC", "MONO", "CUSTOM"]
    assert all(theme["engine"] == "soft_round_led" for theme in themes.values())


def test_theme_intensity_width_position_and_color_are_independent():
    neon = load_universal_themes()["NEON"]
    calm = resolve_universal_profile(neon, "CALM", "COMPACT", "LEFT")
    dynamic = resolve_universal_profile(neon, "DYNAMIC", "WIDE", "RIGHT")
    custom = resolve_universal_profile(neon, "STANDARD", "STANDARD", "CENTER", ["#112233", "#AABBCC"])
    assert calm["amplitude_gain"] < dynamic["amplitude_gain"]
    assert calm["active_width"] == 360 and dynamic["active_width"] == 560
    assert calm["x_position"] == 70 and dynamic["x_position"] == 330
    assert custom["x_position"] == 250
    assert custom["gradient_stops"] == [[0.0, "#112233"], [1.0, "#AABBCC"]]
    assert custom["color_mode"] == "CUSTOM"


def test_theme_json_is_hot_loaded_by_filename_pattern():
    expected = {json.loads(path.read_text(encoding="utf-8"))["id"] for path in THEMES.glob("theme_*.json") if path.name != "theme_order.json"}
    assert set(load_universal_themes()) == expected
    source = (ROOT / "tools/visualizer_prototypes/soft_round_led_engine.py").read_text(encoding="utf-8")
    assert 'glob("theme_*.json")' in source


def test_auto_adapt_reacts_only_with_safe_render_multipliers():
    quiet = np.full((100, 64), .03, np.float32)
    loud = np.full((100, 64), .55, np.float32)
    dark = auto_adapt(quiet, .15); bright = auto_adapt(loud, .80)
    assert dark["amplitude_multiplier"] > 1
    assert dark["glow_multiplier"] > 1
    assert bright["amplitude_multiplier"] < 1
    assert bright["opacity_multiplier"] > 1
    assert bright["brightness_multiplier"] > 1


def test_renderer_core_has_no_channel_specific_names():
    source = (ROOT / "tools/visualizer_prototypes/soft_round_led_engine.py").read_text(encoding="utf-8").lower()
    for forbidden in ("tokyo", "senior", "chanson", "old pop", "japanese"):
        assert forbidden not in source


def test_cross_genre_outputs_and_contact_sheets_exist():
    output = ROOT / "validation_results/universal_theme_system"
    for genre in ("chill", "slow", "chanson_jazz"):
        for theme in ("neon", "warm", "elegant", "soft", "energetic", "mono", "custom"):
            assert (output / f"{genre}_{theme}_wave.mp4").is_file()
            assert (output / f"{genre}_{theme}_composition.mp4").is_file()
    for name in ("universal_7theme_wave.png", "universal_7theme_dark.png", "universal_7theme_bright.png",
                 "cross_genre_theme_matrix.png", "universal_theme_report.json", "universal_theme_report.txt"):
        assert (output / name).is_file()


def test_production_version_stays_frozen():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == "0.8.4.0"
