import json
from pathlib import Path

import numpy as np

from animation.engine import AnimationEngine
from audio.analyzer import analyze_pcm
from render.renderer import CPURenderer, RendererFactory
from template_system import list_templates, load_template
from visualizers.auto_adapt import amplitude_multiplier, background_adjustment


ROOT = Path(__file__).resolve().parents[1]


def universal_template():
    return load_template(ROOT / "templates/00_universal_soft_round_led.json")


def test_auto_adapt_audio_and_background_ranges():
    quiet = amplitude_multiplier({"integrated_dbfs": -38, "dynamic_range_db": 15, "crest_factor": 5, "silence_ratio": .1})
    loud = amplitude_multiplier({"integrated_dbfs": -7, "dynamic_range_db": 4, "crest_factor": 2, "silence_ratio": 0})
    assert 1.15 <= quiet <= 1.35 and .82 <= loud <= 1.0 and quiet > loud
    dark, bright = background_adjustment(.12), background_adjustment(.85)
    assert dark["blend_mode"] == "DARK" and bright["blend_mode"] == "BRIGHT"
    assert dark["glow_multiplier"] > bright["glow_multiplier"]


def test_analyzer_persists_true_source_loudness_and_animation_gain():
    sr = 24000; tone = np.sin(np.arange(sr) * 2 * np.pi * 220 / sr).astype(np.float32) * .02
    features = analyze_pcm(tone, sr, fps=24, bands=64)
    assert float(features["source_integrated_dbfs"][0]) < -30
    engine = AnimationEngine(features, universal_template()); state = engine.sample(.2)
    assert state["auto_gain"] > 1.15


def test_factory_selects_family_and_legacy_templates_still_load():
    renderer = RendererFactory.create("AUTO", universal_template())
    assert renderer.name == "CPU/SOFT_ROUND_LED"
    legacy = load_template(ROOT / "templates/01_clean_bars.json")
    assert not legacy.get("renderer_family")
    assert CPURenderer().render_rgba(320, 160, {"values": np.ones(legacy["bands"], np.float32) * .4}, legacy).shape == (160, 320, 4)


def test_existing_templates_and_universal_template_load_together():
    entries = list_templates(ROOT / "templates", ROOT / "my_templates")
    assert len(entries) >= 76
    assert any(data.get("id") == "UNIVERSAL_SOFT_ROUND_LED" for _path, data in entries)


def test_user_template_snapshot_is_json_queue_safe():
    template = universal_template(); template["universal_visualizer"]["colors"] = ["#112233", "#AABBCC"]
    template["universal_visualizer"]["color_mode"] = "CUSTOM"
    assert json.loads(json.dumps(template))["universal_visualizer"]["colors"] == ["#112233", "#AABBCC"]
