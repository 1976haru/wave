from pathlib import Path

import numpy as np

from tools.visualizer_prototypes.final_led_dot_bakeoff import STYLES, geometry, render


ROOT = Path(__file__).resolve().parents[1]


def test_bakeoff_keeps_production_version_and_five_distinct_candidates():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == "0.8.3.9"
    assert [style.key for style in STYLES] == list("ABCDE")
    assert len({(s.bands, s.active_width, s.diameter, s.attack, s.release) for s in STYLES}) == 5


def test_geometry_is_compact_dot_only_without_visible_baseline():
    spectrum = np.linspace(.22, .92, 64, dtype=np.float32)
    for style in STYLES:
        dots = geometry(style, spectrum)
        assert dots
        xs = [dot[0] for dot in dots]
        ys = [dot[1] for dot in dots]
        assert min(xs) >= 55
        assert max(xs) <= 500
        assert max(xs) - min(xs) <= 430
        assert min(ys) >= 45
        assert max(ys) == 139


def test_round_dot_render_has_no_contour_or_baseline_span():
    spectrum = np.linspace(.15, .95, 64, dtype=np.float32)
    for style in STYLES:
        frame = render(style, spectrum)
        assert frame.shape == (160, 960, 3)
        # Inspect solid/inner cores; the intentionally soft outer halo may
        # overlap horizontally but is not geometry or a baseline.
        active = np.max(frame, axis=2) > 80
        # A continuous baseline or contour would occupy hundreds of pixels in
        # one row. Discrete LED cores remain well below that threshold.
        assert int(active.sum(axis=1).max()) < 260


def test_required_bakeoff_artifacts_exist():
    output = ROOT / "validation_results/final_led_dot_bakeoff"
    names = [
        "A_R1_PURE.mp4", "B_R1_SOFT_DOT.mp4", "C_R1_TOKYO_COLOR.mp4",
        "D_SOFT_DYNAMIC.mp4", "E_CLUB_CHILL.mp4",
        *(f"{key}_{mode}.mp4" for mode in ("mid", "dark") for key in "ABCDE"),
        "final_5style_wave_only.png", "final_5style_mid.png", "final_5style_dark.png",
        "final_5style_reference_compare.png", "bakeoff_report.txt", "bakeoff_report.json",
    ]
    assert all((output / name).is_file() for name in names)
