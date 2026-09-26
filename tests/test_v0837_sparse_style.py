from pathlib import Path
import json

import numpy as np

from render.renderer import signature_instances


ROOT = Path(__file__).parents[1]
PATHS = sorted((ROOT / "templates").glob("00_v0834_tokyo_chill_*.json"))


def templates():
    return [json.loads(path.read_text(encoding="utf-8")) for path in PATHS]


def geometry(template, level, onset=0.0, seconds=4.0):
    count = int(template["bands"])
    values = np.linspace(level * .75, level, count, dtype=np.float32)
    state = {
        "values": values,
        "left_values": np.roll(values, 1) * .97,
        "right_values": np.roll(values, -2) * 1.02,
        "bass": level,
        "mid": level * .85,
        "high": level * .60,
        "onset": onset,
        "time": seconds,
    }
    return signature_instances(960, 160, state, template)


def test_sparse_neon_template_contract():
    by_id = {template["id"]: template for template in templates()}
    assert {key: value["bands"] for key, value in by_id.items()} == {
        "TOKYO_CHILL_HIS": 39,
        "TOKYO_CHILL_DUAL": 41,
        "TOKYO_CHILL_HER": 43,
    }
    assert all(template["version"] == "0.8.3.9" for template in by_id.values())
    assert all(template["column_limit"] <= 6 for template in by_id.values())
    assert all(template["baseline_y"] == template["anchor_y"] == .82 for template in by_id.values())


def test_quiet_geometry_is_sparse_and_floor_anchored():
    for template in templates():
        dots, lines = geometry(template, .18)
        base = 160 * template["anchor_y"]
        baseline_dots = [dot for dot in dots if abs(dot[1] - base) <= .05]
        assert len(baseline_dots) <= int(np.ceil(template["bands"] / 3))
        assert len(dots) < template["bands"] * template["column_limit"] * .78
        assert max(dot[1] for dot in dots) <= base + .05
        assert max(float(np.asarray(layer["points"])[:, 1].max()) for layer in lines) <= base + .05


def test_strong_geometry_keeps_range_with_limited_colour_hierarchy():
    for template in templates():
        quiet, _ = geometry(template, .18)
        strong, _ = geometry(template, .86, .80)
        base = 160 * template["anchor_y"]
        quiet_height = base - min(dot[1] for dot in quiet)
        strong_height = base - min(dot[1] for dot in strong)
        assert strong_height >= quiet_height + 45
        assert strong_height >= 85
        assert 4 <= len({dot[3] for dot in strong}) <= 10
