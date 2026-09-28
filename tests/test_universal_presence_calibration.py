from pathlib import Path

import numpy as np

from tools.visualizer_prototypes.soft_round_led_engine import (
    auto_adapt, dot_geometry, load_modifiers, load_universal_themes,
    render_frame, resolve_universal_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def test_presence_width_presets_are_composition_scaled():
    widths = load_modifiers()["width"]
    assert 340 <= widths["COMPACT"]["active_width"] <= 380
    assert 440 <= widths["STANDARD"]["active_width"] <= 480
    assert 520 <= widths["WIDE"]["active_width"] <= 600


def test_theme_amplitude_personality_order_is_preserved():
    themes = load_universal_themes()
    values = {key: value["amplitude_gain"] for key, value in themes.items()}
    assert values["SOFT"] < values["WARM"] < values["MONO"] < values["ELEGANT"] < values["NEON"] < values["ENERGETIC"]
    assert .78 <= values["SOFT"] <= .88
    assert 1.15 <= values["ENERGETIC"] <= 1.28


def test_audio_level_stats_produce_distinct_bounded_gain():
    spectrum = np.full((100, 64), .2, np.float32)
    quiet = {"integrated_dbfs": -38, "dynamic_range_db": 18, "crest_factor": 5, "silence_ratio": .2}
    normal = {"integrated_dbfs": -20, "dynamic_range_db": 12, "crest_factor": 3, "silence_ratio": 0}
    loud = {"integrated_dbfs": -7, "dynamic_range_db": 5, "crest_factor": 2, "silence_ratio": 0}
    gains = [auto_adapt(spectrum, .5, stats)["amplitude_multiplier"] for stats in (quiet, normal, loud)]
    assert 0.82 <= min(gains) <= max(gains) <= 1.35
    assert gains[0] > gains[1] > gains[2]
    assert len({round(value, 3) for value in gains}) == 3


def test_background_adaptation_is_continuous_and_mode_specific():
    spectrum = np.full((100, 64), .2, np.float32)
    stats = {"integrated_dbfs": -20, "dynamic_range_db": 12, "crest_factor": 3, "silence_ratio": 0}
    dark, mid, bright = (auto_adapt(spectrum, level, stats) for level in (.15, .48, .82))
    assert dark["blend_mode"] == "DARK" and mid["blend_mode"] == "MID" and bright["blend_mode"] == "BRIGHT"
    assert dark["glow_multiplier"] > mid["glow_multiplier"] > bright["glow_multiplier"]
    assert dark["normal_mix"] < mid["normal_mix"] < bright["normal_mix"]
    assert bright["opacity_multiplier"] > mid["opacity_multiplier"]


def test_soft_round_led_geometry_remains_dot_only_and_upward():
    theme = load_universal_themes()["NEON"]
    profile = resolve_universal_profile(theme, "STANDARD", "STANDARD", "LEFT")
    dots = dot_geometry(profile, np.linspace(.1, .9, 64, dtype=np.float32))
    assert dots and all(dot[1] <= profile["floor_y"] for dot in dots)
    assert not any(key in profile for key in ("baseline", "top_contour", "hero_peak", "gaussian_mound"))
    frame = render_frame(profile, np.linspace(.1, .9, 64, dtype=np.float32))
    assert frame.shape == (160, 960, 3) and frame.max() > 0


def test_presence_outputs_cover_35_combinations_when_generated():
    output = ROOT / "validation_results/universal_presence_calibration"
    if not output.exists():
        return
    themes = ("neon", "warm", "elegant", "soft", "energetic", "mono", "custom")
    audios = ("a_quiet", "b_slow", "c_chill", "d_pop", "e_compressed")
    assert all((output / f"{audio}_{theme}_mid.mp4").is_file() for audio in audios for theme in themes)
    for name in ("universal_presence_wave.png", "universal_presence_dark.png", "universal_presence_mid.png",
                 "universal_presence_bright.png", "cross_genre_presence_matrix.png",
                 "universal_presence_report.json", "universal_presence_report.txt"):
        assert (output / name).is_file()


def test_production_version_remains_frozen():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == "0.8.4.1"
