from pathlib import Path
import json

import numpy as np

from render.renderer import signature_instances


ROOT = Path(__file__).parents[1]
PATHS = sorted((ROOT / "templates").glob("00_v0834_tokyo_chill_*.json"))


def templates():
    return [json.loads(path.read_text(encoding="utf-8")) for path in PATHS]


def geometry(template, level=.82, onset=.75):
    count = int(template["bands"])
    values = np.linspace(level * .72, level, count, dtype=np.float32)
    state = {
        "values": values,
        "left_values": np.roll(values, 1) * .97,
        "right_values": np.roll(values, -2) * 1.02,
        "bass": level,
        "mid": level * .85,
        "high": level * .60,
        "onset": onset,
        "time": 4.0,
    }
    return signature_instances(960, 160, state, template)


def test_top_contour_is_completely_removed():
    for template in templates():
        _, lines = geometry(template)
        base = 160 * template["anchor_y"]
        assert len(lines) == 2
        assert all(np.allclose(np.asarray(layer["points"])[:, 1], base) for layer in lines)


def test_premium_dots_stay_above_floor_with_reduced_fill():
    for template in templates():
        dots, lines = geometry(template)
        base = 160 * template["anchor_y"]
        assert max(dot[1] for dot in dots) <= base + .05
        assert max(float(np.asarray(layer["points"])[:, 1].max()) for layer in lines) <= base + .05
        assert len(dots) < template["bands"] * 3


def test_hero_accents_are_limited_and_dynamic_range_survives():
    for template in templates():
        quiet, _ = geometry(template, .18, 0)
        strong, _ = geometry(template, .86, .80)
        base = 160 * template["anchor_y"]
        quiet_height = base - min(dot[1] for dot in quiet)
        strong_height = base - min(dot[1] for dot in strong)
        radius = template["dot_diameter"] / 2
        accents = [dot for dot in strong if dot[2] >= radius * 1.12]
        assert strong_height >= quiet_height + 45
        assert strong_height >= 85
        assert 1 <= len(accents) <= 7
