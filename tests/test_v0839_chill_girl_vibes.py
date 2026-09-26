from pathlib import Path
import json

import numpy as np

from render.renderer import signature_instances


ROOT = Path(__file__).parents[1]
PATHS = sorted((ROOT / "templates").glob("00_v0834_tokyo_chill_*.json"))


def templates():
    return [json.loads(path.read_text(encoding="utf-8")) for path in PATHS]


def geometry(template, level, onset=0.0):
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


def test_chill_girl_template_contract():
    by_id = {template["id"]: template for template in templates()}
    assert {key: value["bands"] for key, value in by_id.items()} == {
        "TOKYO_CHILL_HIS": 39,
        "TOKYO_CHILL_DUAL": 41,
        "TOKYO_CHILL_HER": 43,
    }
    assert all(template["version"] == "0.8.3.9" for template in by_id.values())
    assert all(.80 <= template["width"] <= .86 for template in by_id.values())
    assert all(template["baseline_y"] == template["anchor_y"] == .82 for template in by_id.values())


def test_dotted_body_density_is_visible_but_not_a_wall():
    for template in templates():
        quiet, _ = geometry(template, .18)
        medium, _ = geometry(template, .48, .25)
        strong, _ = geometry(template, .86, .80)
        assert 40 <= len(quiet) <= 100
        assert 70 <= len(medium) <= 160
        assert 90 <= len(strong) <= 190
        assert len(quiet) < len(medium) < len(strong)


def test_body_is_floor_anchored_without_top_contour_or_harsh_marker():
    for template in templates():
        dots, lines = geometry(template, .86, .80)
        base = 160 * template["anchor_y"]
        assert len(lines) == 2
        assert all(np.allclose(np.asarray(layer["points"])[:, 1], base) for layer in lines)
        assert max(dot[1] for dot in dots) <= base + .05
        assert max(max(dot[3]) for dot in dots) <= 255
        assert template["highlight_color"] not in {"#FFFFFF", "#FFF3FA", "#EAF6FF"}
