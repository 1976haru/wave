from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from core.paths import resource_path
from visualizers.auto_adapt import background_adjustment
from visualizers.local_background import (
    adaptation_from_metrics, analyze_local_background, derive_underlay_color,
    smooth_adaptation, waveform_roi,
)

PROFILE_DIR = Path(resource_path("visualizers/profiles"))
SUPPORTED_PARAMETERS = ("theme", "intensity", "width", "position", "color_mode", "colors", "auto_adapt", "local_adapt", "advanced")


@lru_cache(maxsize=1)
def load_profiles() -> tuple[dict, dict, dict]:
    base = json.loads((PROFILE_DIR / "base_soft_round_led.json").read_text(encoding="utf-8"))
    modifiers = json.loads((PROFILE_DIR / "modifiers.json").read_text(encoding="utf-8"))
    themes = {}
    for path in PROFILE_DIR.glob("theme_*.json"):
        theme = json.loads(path.read_text(encoding="utf-8")); themes[theme["id"]] = theme
    return base, modifiers, themes


def _hex_rgb(value: str) -> tuple[int, int, int]:
    text = str(value).lstrip("#"); return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def resolve_profile(template: dict, width: int, height: int, state: dict | None = None) -> dict:
    base, modifiers, themes = load_profiles(); settings = template.get("universal_visualizer", template)
    theme_id = str(settings.get("theme", "NEON")).upper(); profile = {**base, **themes.get(theme_id, themes["NEON"])}
    intensity = str(settings.get("intensity", "STANDARD")).upper(); width_id = str(settings.get("width", "STANDARD")).upper()
    position = str(settings.get("position", "LEFT")).upper(); values = modifiers["intensity"].get(intensity, modifiers["intensity"]["STANDARD"])
    profile["amplitude_gain"] *= values["amplitude_multiplier"]
    profile["attack"] = float(np.clip(profile["attack"] * values["attack_multiplier"], .02, .95))
    profile["release"] = float(np.clip(profile["release"] + values["release_offset"], .5, .99))
    profile["active_width"] = modifiers["width"].get(width_id, modifiers["width"]["STANDARD"])["active_width"] * width / 960
    margin = modifiers["position"].get(position, modifiers["position"]["LEFT"])["margin"] * width / 960
    profile["x_position"] = margin if position == "LEFT" else ((width - profile["active_width"]) / 2 if position == "CENTER" else width - profile["active_width"] - margin)
    profile["y_position"] = height * .87
    if str(settings.get("color_mode", "THEME")).upper() == "CUSTOM" and 2 <= len(settings.get("colors", [])) <= 4:
        colors = settings["colors"]; profile["gradient_stops"] = [[i / (len(colors) - 1), color] for i, color in enumerate(colors)]
    advanced = settings.get("advanced", {})
    for key, value in advanced.items():
        if key in profile and key != "glow_radius": profile[key] = value
    if "glow_strength" in advanced:
        profile["inner_glow_alpha"] *= float(advanced["glow_strength"])
        profile["outer_glow_alpha"] *= float(advanced["glow_strength"])
    if "glow_radius" in advanced:
        radius = float(advanced["glow_radius"]); profile["glow_radius"] = [max(1.0, radius * .62), max(1.4, radius)]
    profile["x_position"] += float(advanced.get("x_offset", 0)) * width / 960
    profile["y_position"] += float(advanced.get("y_offset", 0)) * height / 160
    if settings.get("auto_adapt", True):
        profile["amplitude_gain"] *= float((state or {}).get("auto_gain", 1.0))
        adjustment = background_adjustment(float(settings.get("advanced", {}).get("background_brightness", .5)))
        profile["overall_opacity"] *= adjustment["opacity_multiplier"]
        profile["brightness_compensation"] *= adjustment["brightness_multiplier"]
        profile["inner_glow_alpha"] *= adjustment["glow_multiplier"]
        profile["outer_glow_alpha"] *= adjustment["glow_multiplier"]
    return profile


def _color_at(stops: list, position: float, level: float, brightness: float) -> tuple[int, int, int]:
    stops = sorted(stops, key=lambda item: item[0]); position = float(np.clip(position, 0, 1)); lower, upper = stops[0], stops[-1]
    for left, right in zip(stops, stops[1:]):
        if left[0] <= position <= right[0]: lower, upper = left, right; break
    mix = (position - lower[0]) / max(1e-6, upper[0] - lower[0])
    first, second = np.asarray(_hex_rgb(lower[1]), np.float32), np.asarray(_hex_rgb(upper[1]), np.float32)
    return tuple(int(np.clip(value, 0, 255)) for value in (first * (1 - mix) + second * mix) * brightness * (.82 + .18 * level))


def _adapt_color(color: tuple[int, int, int], brightness: float, saturation: float) -> np.ndarray:
    value = np.asarray(color, np.float32) / 255.0
    gray = float(np.dot(value, (.2126, .7152, .0722)))
    value = gray + (value - gray) * saturation
    return np.clip(value * brightness * 255.0, 0, 255)


@lru_cache(maxsize=96)
def _color_lut(stops_key: tuple, brightness_key: int, bands: int, rows: int) -> np.ndarray:
    stops = [[position, color] for position, color in stops_key]
    brightness = brightness_key / 1000
    return np.asarray([[_color_at(stops, column / max(1, bands - 1), row / max(1, rows - 1), brightness)
                        for row in range(rows)] for column in range(bands)], np.uint8)


def _map_bands(values: np.ndarray, profile: dict) -> np.ndarray:
    source = np.asarray(values, np.float32); count = int(profile["bands"])
    frequencies = np.geomspace(float(profile["min_frequency"]), float(profile["max_frequency"]), count)
    positions = (np.log(frequencies) - math.log(20)) / (math.log(20000) - math.log(20)) * (len(source) - 1)
    result = np.interp(np.clip(positions, 0, len(source) - 1), np.arange(len(source)), source)
    for _ in range(int(profile["temporal_smoothing"])):
        result = np.convolve(np.pad(result, (1, 1), mode="edge"), (.18, .64, .18), mode="valid")
    for indices, key in zip(np.array_split(np.arange(count), 3), ("low_band_weight", "mid_band_weight", "high_band_weight")):
        result[indices] *= float(profile[key])
    return np.clip(result * float(profile["amplitude_gain"]), 0, 1)


def dot_geometry(profile: dict, values: np.ndarray) -> list[tuple[float, float, float, tuple[int, int, int], float]]:
    data = np.power(_map_bands(values, profile), .66) * np.linspace(1, .70, int(profile["bands"]), dtype=np.float32)
    xs = np.linspace(float(profile["x_position"]), float(profile["x_position"]) + float(profile["active_width"]), len(data))
    threshold = float(profile["tail_threshold"]); dots = []
    maximum = int(profile["amplitude_ceiling"])
    stops_key = tuple((float(position), str(color)) for position, color in profile["gradient_stops"])
    colors = _color_lut(stops_key, round(float(profile["brightness_compensation"]) * 1000), len(data), maximum)
    for index, (x, energy) in enumerate(zip(xs, data)):
        if energy < threshold: continue
        minimum = int(profile["amplitude_floor"])
        count = int(np.clip(minimum + (energy - threshold) / (1 - threshold) * (maximum - minimum), minimum, maximum))
        for row in range(count):
            level = row / max(1, count - 1)
            dots.append((float(x), float(profile["y_position"]) - row * float(profile["vertical_gap"]),
                         float(profile["dot_diameter"]) / 2, tuple(map(int, colors[index, min(row, maximum - 1)])),
                         float(profile["core_alpha"]) * float(profile["overall_opacity"])))
    return dots


@lru_cache(maxsize=96)
def _sprite(radius_key, core_key, inner_key, outer_key, inner_scale_key, outer_scale_key):
    radius = radius_key / 100; extent = max(5, math.ceil(radius * outer_scale_key / 100 + 5)); scale = 4; size = extent * 2 + 1
    mask = np.zeros((size * scale, size * scale), np.float32); center = (extent * scale + scale // 2,) * 2
    cv2.circle(mask, center, max(1, round(radius * scale)), 1, -1, cv2.LINE_AA)
    core = mask * core_key / 1000
    inner = cv2.GaussianBlur(mask, (0, 0), max(.5, radius * inner_scale_key / 100 * scale * .38)) * inner_key / 1000
    outer = cv2.GaussianBlur(mask, (0, 0), max(.8, radius * outer_scale_key / 100 * scale * .62)) * outer_key / 1000
    return cv2.resize(np.clip(core + inner + outer, 0, 1), (size, size), interpolation=cv2.INTER_AREA)[..., None]


@lru_cache(maxsize=64)
def _underlay_sprite(radius_key: int, alpha_key: int, growth_key: int) -> np.ndarray:
    radius = radius_key / 100 + growth_key / 100
    extent = max(4, math.ceil(radius + 2)); scale = 4; size = extent * 2 + 1
    mask = np.zeros((size * scale, size * scale), np.float32); center = (extent * scale + scale // 2,) * 2
    cv2.circle(mask, center, max(1, round(radius * scale)), alpha_key / 1000, -1, cv2.LINE_AA)
    return cv2.resize(mask, (size, size), interpolation=cv2.INTER_AREA)[..., None]


def _paint(frame: np.ndarray, sprite: np.ndarray, cx: int, cy: int, color: np.ndarray) -> None:
    half = sprite.shape[0] // 2; height, width = frame.shape[:2]
    left, top = max(0, cx - half), max(0, cy - half)
    right, bottom = min(width, cx - half + sprite.shape[1]), min(height, cy - half + sprite.shape[0])
    if left >= right or top >= bottom:
        return
    sx, sy = left - (cx - half), top - (cy - half)
    patch = sprite[sy:sy + bottom - top, sx:sx + right - left]
    frame[top:bottom, left:right] += patch * color


class SoftRoundLEDRenderer:
    name = "CPU/SOFT_ROUND_LED"
    def __init__(self):
        self._local_adaptation = None
        self._frame_index = 0
        self.last_local_metrics = None

    def render_rgba(self, width: int, height: int, state: dict, template: dict) -> np.ndarray:
        profile = resolve_profile(template, width, height, state); frame = np.zeros((height, width, 3), np.float32)
        coverage = np.zeros_like(frame)
        settings = template.get("universal_visualizer", template)
        background = state.get("background_frame")
        if settings.get("local_adapt", True) and background is not None:
            background = np.asarray(background)
            if background.shape[:2] != (height, width):
                background = cv2.resize(background, (width, height), interpolation=cv2.INTER_AREA)
            # Sample every third frame and interpolate with EMA to avoid both cost and flicker.
            if self._frame_index % 3 == 0 or self._local_adaptation is None:
                metrics = analyze_local_background(background, waveform_roi(profile, width, height))
                current = adaptation_from_metrics(metrics)
                self._local_adaptation = smooth_adaptation(self._local_adaptation, current)
                self.last_local_metrics = metrics
            local = self._local_adaptation
        else:
            local = {"difficulty": 0.0, "underlay_alpha": 0.0, "underlay_scale": .55,
                     "core_alpha_multiplier": 1.0, "core_brightness_multiplier": 1.0,
                     "core_saturation_multiplier": 1.0, "glow_multiplier": 1.0}
        self._frame_index += 1
        glow = profile["glow_radius"]
        glow_multiplier = local["glow_multiplier"]
        sprite = _sprite(round(profile["dot_diameter"] / 2 * 100), round(min(1.0, profile["core_alpha"] * profile["overall_opacity"] * local["core_alpha_multiplier"]) * 1000),
                         round(profile["inner_glow_alpha"] * glow_multiplier * 1000), round(profile["outer_glow_alpha"] * glow_multiplier * 1000),
                         round(glow[0] * 100), round(glow[1] * 100))
        underlay = _underlay_sprite(round(profile["dot_diameter"] / 2 * 100), round(local["underlay_alpha"] * 1000), round(local["underlay_scale"] * 100))
        theme = str(settings.get("theme", "NEON"))
        if str(settings.get("color_mode", "THEME")).upper() == "CUSTOM": theme = "CUSTOM"
        underlay_color = np.asarray(derive_underlay_color(profile["gradient_stops"], theme), np.float32)
        for x, y, _radius, color, _alpha in dot_geometry(profile, state["values"]):
            cx, cy = round(x), round(y)
            if local["underlay_alpha"] > 0:
                _paint(frame, underlay, cx, cy, underlay_color)
                _paint(coverage, underlay, cx, cy, np.full(3, 255, np.float32))
            core_color = _adapt_color(color, local["core_brightness_multiplier"], local["core_saturation_multiplier"])
            _paint(frame, sprite, cx, cy, core_color)
            _paint(coverage, sprite, cx, cy, np.full(3, 255, np.float32))
        rgb = np.clip(frame, 0, 255).astype(np.uint8); alpha = np.max(np.clip(coverage, 0, 255).astype(np.uint8), axis=2)
        return np.dstack((rgb, alpha))
