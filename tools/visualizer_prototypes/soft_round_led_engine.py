from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "research/visualizer_candidates/visualizer_profiles"


def load_profiles() -> list[dict]:
    base = json.loads((PROFILE_DIR / "base_soft_round_led.json").read_text(encoding="utf-8"))
    profiles = []
    for filename in ("tokyo_chill.json", "senior_oldpop.json", "chanson_paris.json"):
        channel = json.loads((PROFILE_DIR / filename).read_text(encoding="utf-8"))
        for key, overrides in channel["variants"].items():
            profile = {**base, **overrides, "key": key, "channel": channel["channel"],
                       "style_name": channel["style_name"], "audio": channel["audio"],
                       "background": channel["background"], "background_treatment": channel["background_treatment"],
                       "placement": channel["placement"]}
            profiles.append(profile)
    return profiles


def hex_bgr(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return blue, green, red


def color_at(stops: list, position: float, level: float, brightness: float) -> tuple[int, int, int]:
    stops = sorted(stops, key=lambda item: item[0]); position = float(np.clip(position, 0, 1))
    lower, upper = stops[0], stops[-1]
    for left, right in zip(stops, stops[1:]):
        if left[0] <= position <= right[0]:
            lower, upper = left, right; break
    mix = (position - lower[0]) / max(1e-6, upper[0] - lower[0])
    first, second = np.asarray(hex_bgr(lower[1]), np.float32), np.asarray(hex_bgr(upper[1]), np.float32)
    color = (first * (1 - mix) + second * mix) * brightness * (.82 + .18 * level)
    return tuple(int(np.clip(value, 0, 255)) for value in color)


def map_bands(values: np.ndarray, profile: dict) -> np.ndarray:
    source = np.asarray(values, np.float32); count = int(profile["bands"])
    low_hz, high_hz = float(profile["frequency_min"]), float(profile["frequency_max"])
    frequencies = np.geomspace(low_hz, high_hz, count)
    positions = (np.log(frequencies) - math.log(20)) / (math.log(20000) - math.log(20)) * (len(source) - 1)
    result = np.interp(np.clip(positions, 0, len(source) - 1), np.arange(len(source)), source)
    for _ in range(int(profile["smoothing"])):
        result = np.convolve(np.pad(result, (1, 1), mode="edge"), (.18, .64, .18), mode="valid")
    thirds = np.array_split(np.arange(count), 3)
    for indices, key in zip(thirds, ("low_band_weight", "mid_band_weight", "high_band_weight")):
        result[indices] *= float(profile[key])
    return np.clip(result * float(profile["amplitude_gain"]), 0, 1).astype(np.float32)


def dot_geometry(profile: dict, values: np.ndarray) -> list[tuple[float, float, float, tuple[int, int, int], float]]:
    data = np.power(map_bands(values, profile), .66)
    data *= np.linspace(1.0, .70, len(data), dtype=np.float32)
    x0, width = float(profile["x_position"]), float(profile["active_width"])
    xs = np.linspace(x0, x0 + width, len(data)); threshold = float(profile["tail_threshold"])
    dots = []
    for index, (x, energy) in enumerate(zip(xs, data)):
        if energy < threshold:
            continue
        maximum = int(profile["max_dot_count"]); minimum = int(profile["min_dot_count"])
        count = int(np.clip(minimum + (energy - threshold) / (1 - threshold) * (maximum - minimum), minimum, maximum))
        for row in range(count):
            level = row / max(1, count - 1)
            color = color_at(profile["gradient_stops"], index / max(1, len(data) - 1), level, float(profile["brightness"]))
            dots.append((float(x), float(profile["floor_y"]) - row * float(profile["vertical_gap"]),
                         float(profile["dot_diameter"]) / 2, color, float(profile["core_alpha"]) * float(profile["opacity"])))
    return dots


def render_frame(profile: dict, values: np.ndarray, width=960, height=160) -> np.ndarray:
    # Two-times supersampling provides circular antialiasing while keeping a
    # nine-style research bake-off practical on CPU.
    scale = 2
    core = np.zeros((height * scale, width * scale, 3), np.float32)
    inner = np.zeros_like(core); outer = np.zeros_like(core)
    for x, y, radius, color, alpha in dot_geometry(profile, values):
        center = (round(x * scale), round(y * scale)); rgb = tuple(float(channel) for channel in color)
        cv2.circle(outer, center, max(1, round(radius * float(profile["outer_glow_scale"]) * scale)), rgb, -1, cv2.LINE_AA)
        cv2.circle(inner, center, max(1, round(radius * float(profile["inner_glow_scale"]) * scale)), rgb, -1, cv2.LINE_AA)
        cv2.circle(core, center, max(1, round(radius * scale)), tuple(channel * alpha for channel in rgb), -1, cv2.LINE_AA)
    outer = cv2.GaussianBlur(outer, (0, 0), 2.2 * scale) * float(profile["outer_glow"])
    inner = cv2.GaussianBlur(inner, (0, 0), .75 * scale) * float(profile["inner_glow"])
    return cv2.resize(np.clip(core + inner + outer, 0, 255).astype(np.uint8), (width, height), interpolation=cv2.INTER_AREA)


def robust_normalize(spectrum: np.ndarray) -> np.ndarray:
    spectrum = np.asarray(spectrum, np.float32)
    low = np.percentile(spectrum, 20, axis=0); high = np.percentile(spectrum, 95, axis=0)
    return np.clip((spectrum - low) / np.maximum(high - low, 1e-5), 0, 1).astype(np.float32)
