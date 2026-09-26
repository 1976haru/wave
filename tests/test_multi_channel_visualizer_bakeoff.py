from pathlib import Path

import numpy as np

from tools.visualizer_prototypes.soft_round_led_engine import load_profiles, render_frame


ROOT = Path(__file__).resolve().parents[1]


def test_shared_engine_loads_nine_profiles_across_three_channels():
    profiles = load_profiles()
    assert [profile["key"] for profile in profiles] == ["T1", "T2", "T3", "S1", "S2", "S3", "C1", "C2", "C3"]
    assert len({profile["channel"] for profile in profiles}) == 3
    assert len({profile["audio"] for profile in profiles}) == 3
    assert all(profile["engine"] == "soft_round_led" for profile in profiles)


def test_profile_parameters_are_data_driven_and_channel_specific():
    profiles = load_profiles()
    required = {"bands", "active_width", "x_position", "dot_diameter", "horizontal_gap", "vertical_gap",
                "core_alpha", "inner_glow", "outer_glow", "attack", "release", "smoothing", "amplitude_gain",
                "min_dot_count", "max_dot_count", "frequency_min", "frequency_max", "gradient_stops", "brightness",
                "opacity", "tail_threshold", "low_band_weight", "mid_band_weight", "high_band_weight"}
    assert all(required <= profile.keys() for profile in profiles)
    tokyo = [p for p in profiles if p["key"].startswith("T")]
    senior = [p for p in profiles if p["key"].startswith("S")]
    chanson = [p for p in profiles if p["key"].startswith("C")]
    assert max(p["attack"] for p in tokyo) > max(p["attack"] for p in senior)
    assert max(p["amplitude_gain"] for p in senior) < min(p["amplitude_gain"] for p in tokyo)
    assert all("#55D8FF" not in {stop[1] for stop in p["gradient_stops"]} for p in senior + chanson)


def test_shared_renderer_remains_dot_only_without_baseline_or_contour():
    spectrum = np.linspace(.18, .94, 64, dtype=np.float32)
    for profile in load_profiles():
        frame = render_frame(profile, spectrum)
        assert frame.shape == (160, 960, 3)
        active = np.max(frame, axis=2) > 80
        assert int(active.sum(axis=1).max()) < 280
        assert not np.any(active[145:])


def test_multi_channel_outputs_exist():
    output = ROOT / "validation_results/multi_channel_visualizer_bakeoff"
    for key in ("T1", "T2", "T3", "S1", "S2", "S3", "C1", "C2", "C3"):
        assert (output / f"{key}_wave.mp4").is_file()
        assert (output / f"{key}_composition.mp4").is_file()
    for name in ("tokyo_3style.png", "senior_3style.png", "chanson_3style.png",
                 "multi_channel_9style_wave.png", "multi_channel_9style_composition.png",
                 "multi_channel_report.txt", "multi_channel_report.json"):
        assert (output / name).is_file()


def test_production_version_stays_frozen():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == "0.8.3.9"
