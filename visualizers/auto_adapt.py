from __future__ import annotations

import numpy as np


def audio_presence_from_features(features: dict) -> dict:
    def scalar(name, default):
        value = features.get(name)
        return float(np.asarray(value).reshape(-1)[0]) if value is not None else default
    return {"integrated_dbfs": scalar("source_integrated_dbfs", -20),
            "p20_dbfs": scalar("source_p20_dbfs", -26), "median_dbfs": scalar("source_median_dbfs", -20),
            "p95_dbfs": scalar("source_p95_dbfs", -14), "crest_factor": scalar("source_crest_factor", 3),
            "dynamic_range_db": scalar("source_dynamic_range_db", 12),
            "silence_ratio": scalar("source_silence_ratio", 0),
            "transient_density": scalar("source_transient_density", .05)}


def amplitude_multiplier(stats: dict) -> float:
    level = float(stats.get("integrated_dbfs", -20))
    gain = float(np.interp(level, [-42, -32, -24, -16, -10, -4], [1.35, 1.28, 1.15, 1.00, .88, .82]))
    gain += float(np.clip((stats.get("dynamic_range_db", 10) - 12) * .004, -.035, .035))
    gain += float(np.clip((stats.get("crest_factor", 3) - 4) * .008, -.025, .025))
    gain += min(.04, float(stats.get("silence_ratio", 0)) * .08)
    return float(np.clip(gain, .82, 1.35))


def background_adjustment(brightness: float) -> dict:
    value = float(np.clip(brightness, 0, 1))
    bright = float(np.clip((value - .30) / .45, 0, 1)); dark = float(np.clip((.30 - value) / .30, 0, 1))
    return {"opacity_multiplier": 1 + .20 * bright - .01 * dark,
            "brightness_multiplier": 1 + .28 * bright, "glow_multiplier": 1 + .12 * dark - .16 * bright,
            "normal_mix": .66 * bright, "contrast_halo": .10 * bright,
            "blend_mode": "BRIGHT" if bright >= .78 else ("DARK" if dark >= .34 else "MID")}
