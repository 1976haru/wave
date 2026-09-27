from __future__ import annotations

import json
import math
import subprocess
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
UNIVERSAL_THEME_DIR = ROOT / "research/visualizer_candidates/universal_themes"


def load_universal_themes(directory: Path = UNIVERSAL_THEME_DIR) -> dict[str, dict]:
    """Auto-discover generic themes; no channel or theme name lives in renderer code."""
    base = json.loads((directory / "base_soft_round_led.json").read_text(encoding="utf-8"))
    themes = {}
    for path in sorted(directory.glob("theme_*.json")):
        if path.name == "theme_order.json":
            continue
        theme = json.loads(path.read_text(encoding="utf-8"))
        themes[theme["id"].upper()] = {**base, **theme, "source_file": str(path)}
    order_path = directory / "theme_order.json"
    preferred = json.loads(order_path.read_text(encoding="utf-8"))["order"] if order_path.exists() else []
    rank = {theme_id: index for index, theme_id in enumerate(preferred)}
    return dict(sorted(themes.items(), key=lambda item: (rank.get(item[0], len(rank)), item[0])))


def load_modifiers(directory: Path = UNIVERSAL_THEME_DIR) -> dict:
    return json.loads((directory / "modifiers.json").read_text(encoding="utf-8"))


def measure_audio_presence(audio_path: Path, ffmpeg_path: str, sample_rate: int = 24000) -> dict:
    """Measure source-level dynamics before analyzer normalization changes scale."""
    command = [ffmpeg_path, "-v", "error", "-i", str(audio_path), "-ac", "1", "-ar", str(sample_rate),
               "-f", "f32le", "pipe:1"]
    decoded = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
    samples = np.frombuffer(decoded, dtype="<f4").astype(np.float32)
    if not len(samples):
        raise RuntimeError(f"No decoded samples: {audio_path}")
    frame_size = max(1, round(sample_rate * .05))
    usable = len(samples) // frame_size * frame_size
    frames = samples[:usable].reshape(-1, frame_size) if usable else samples.reshape(1, -1)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1) + 1e-12)
    db = 20 * np.log10(np.maximum(frame_rms, 1e-7))
    integrated = float(np.sqrt(np.mean(np.square(samples)) + 1e-12))
    integrated_db = float(20 * np.log10(max(integrated, 1e-7)))
    p20, median, p95 = (float(np.percentile(db, value)) for value in (20, 50, 95))
    peak = float(np.max(np.abs(samples)))
    crest = float(peak / max(integrated, 1e-7))
    deltas = np.diff(frame_rms, prepend=frame_rms[0])
    transient_threshold = float(np.median(deltas) + 2.5 * np.median(np.abs(deltas - np.median(deltas))))
    transient_density = float(np.mean(deltas > max(transient_threshold, .001)))

    fft_size = 4096
    chunks = samples[:len(samples) // fft_size * fft_size].reshape(-1, fft_size)
    if len(chunks):
        power = np.mean(np.abs(np.fft.rfft(chunks * np.hanning(fft_size), axis=1)) ** 2, axis=0)
        frequencies = np.fft.rfftfreq(fft_size, 1 / sample_rate)
        totals = []
        for low, high in ((20, 250), (250, 2000), (2000, min(12000, sample_rate / 2))):
            totals.append(float(np.sum(power[(frequencies >= low) & (frequencies < high)])))
        total = max(sum(totals), 1e-12)
        bass, mid, high = (value / total for value in totals)
    else:
        bass = mid = high = 1 / 3
    return {"integrated_rms": integrated, "integrated_dbfs": integrated_db, "p20_dbfs": p20,
            "median_dbfs": median, "p95_dbfs": p95, "crest_factor": crest,
            "dynamic_range_db": p95 - p20, "silence_ratio": float(np.mean(db < -48)),
            "transient_density": transient_density, "bass_balance": bass,
            "mid_balance": mid, "high_balance": high}


def _audio_gain(stats: dict) -> float:
    level = float(stats["integrated_dbfs"])
    anchors = np.asarray([-42, -32, -24, -16, -10, -4], np.float32)
    gains = np.asarray([1.35, 1.28, 1.15, 1.00, .88, .82], np.float32)
    gain = float(np.interp(level, anchors, gains))
    dynamic_range = float(stats.get("dynamic_range_db", 10))
    crest = float(stats.get("crest_factor", 3))
    silence = float(stats.get("silence_ratio", 0))
    gain += np.clip((dynamic_range - 12) * .004, -.035, .035)
    gain += np.clip((crest - 4) * .008, -.025, .025)
    gain += min(.04, silence * .08)
    return float(np.clip(gain, .82, 1.35))


def auto_adapt(spectrum: np.ndarray, background_brightness: float, audio_stats: dict | None = None) -> dict:
    data = np.asarray(spectrum, np.float32)
    frame_energy = np.mean(data, axis=1)
    average = float(np.mean(frame_energy)); crest = float(np.percentile(frame_energy, 95) / max(1e-5, average))
    bands = np.mean(data, axis=0); thirds = np.array_split(bands, 3)
    bass, mid, high = (float(np.mean(part)) for part in thirds)
    if audio_stats:
        gain = _audio_gain(audio_stats)
    else:
        gain = 1.18 if average < .16 else (.90 if average > .38 else 1.04)
        if crest > 3.0: gain *= .96
        gain = float(np.clip(gain, .82, 1.35))
    bright_mix = float(np.clip((background_brightness - .30) / .45, 0, 1))
    dark_mix = float(np.clip((.30 - background_brightness) / .30, 0, 1))
    opacity = 1.0 + .20 * bright_mix - .01 * dark_mix
    brightness = 1.0 + .28 * bright_mix
    glow = 1.0 + .12 * dark_mix - .16 * bright_mix
    normal_mix = .66 * bright_mix
    blend_mode = "BRIGHT" if bright_mix >= .78 else ("DARK" if dark_mix >= .34 else "MID")
    return {"average_audio_energy": average, "crest_factor": crest, "bass_balance": bass,
            "mid_balance": mid, "high_balance": high, "background_brightness": background_brightness,
            "amplitude_multiplier": gain, "opacity_multiplier": opacity,
            "brightness_multiplier": brightness, "glow_multiplier": glow,
            "normal_mix": normal_mix, "contrast_halo": .10 * bright_mix, "blend_mode": blend_mode,
            **({f"audio_{key}": value for key, value in audio_stats.items()} if audio_stats else {})}


def resolve_universal_profile(theme: dict, intensity: str = "STANDARD", width: str = "STANDARD",
                              position: str = "LEFT", custom_colors: list[str] | None = None,
                              adapt: dict | None = None, modifiers: dict | None = None) -> dict:
    modifiers = modifiers or load_modifiers(); intensity = intensity.upper(); width = width.upper(); position = position.upper()
    result = dict(theme); intensity_values = modifiers["intensity"][intensity]
    result["amplitude_gain"] *= intensity_values["amplitude_multiplier"]
    result["attack"] = float(np.clip(result["attack"] * intensity_values["attack_multiplier"], .05, .9))
    result["release"] = float(np.clip(result["release"] + intensity_values["release_offset"], .55, .97))
    result["active_width"] = modifiers["width"][width]["active_width"]
    margin = float(modifiers["position"][position]["margin"])
    if position == "LEFT": result["x_position"] = margin
    elif position == "CENTER": result["x_position"] = (960 - result["active_width"]) / 2
    else: result["x_position"] = 960 - result["active_width"] - margin
    if custom_colors:
        result["gradient_stops"] = [[index / max(1, len(custom_colors)-1), color] for index, color in enumerate(custom_colors)]
        result["color_mode"] = "CUSTOM"
    else:
        result["color_mode"] = "THEME"
    if adapt:
        result["amplitude_gain"] *= adapt["amplitude_multiplier"]
        result["overall_opacity"] *= adapt["opacity_multiplier"]
        result["brightness_compensation"] *= adapt["brightness_multiplier"]
        result["inner_glow_alpha"] *= adapt["glow_multiplier"]
        result["outer_glow_alpha"] *= adapt["glow_multiplier"]
    # Translate the public universal schema once at the engine boundary.
    result.update(floor_y=result["y_position"], inner_glow=result["inner_glow_alpha"],
                  outer_glow=result["outer_glow_alpha"], inner_glow_scale=result["glow_radius"][0],
                  outer_glow_scale=result["glow_radius"][1], frequency_min=result["min_frequency"],
                  frequency_max=result["max_frequency"], opacity=result["overall_opacity"],
                  brightness=result["brightness_compensation"], smoothing=result["temporal_smoothing"],
                  min_dot_count=result["amplitude_floor"], max_dot_count=result["amplitude_ceiling"])
    return result


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


@lru_cache(maxsize=96)
def _dot_sprite(radius_key: int, core_key: int, inner_key: int, outer_key: int,
                inner_scale_key: int, outer_scale_key: int) -> np.ndarray:
    radius = radius_key / 100
    core_alpha, inner_alpha, outer_alpha = core_key / 1000, inner_key / 1000, outer_key / 1000
    inner_scale, outer_scale = inner_scale_key / 100, outer_scale_key / 100
    extent = max(5, int(math.ceil(radius * outer_scale + 5)))
    scale = 4
    size = extent * 2 + 1
    mask = np.zeros((size * scale, size * scale), np.float32)
    center = (extent * scale + scale // 2, extent * scale + scale // 2)
    cv2.circle(mask, center, max(1, round(radius * scale)), 1.0, -1, cv2.LINE_AA)
    core = mask * core_alpha
    inner = cv2.GaussianBlur(mask, (0, 0), max(.5, radius * inner_scale * scale * .38)) * inner_alpha
    outer = cv2.GaussianBlur(mask, (0, 0), max(.8, radius * outer_scale * scale * .62)) * outer_alpha
    combined = cv2.resize(np.clip(core + inner + outer, 0, 1), (size, size), interpolation=cv2.INTER_AREA)
    return combined[..., None]


def render_frame(profile: dict, values: np.ndarray, width=960, height=160) -> np.ndarray:
    """Render cached antialiased dot sprites without frame-sized glow blurs."""
    frame = np.zeros((height, width, 3), np.float32)
    sprite = _dot_sprite(round(float(profile["dot_diameter"]) / 2 * 100),
                         round(float(profile["core_alpha"]) * float(profile["opacity"]) * 1000),
                         round(float(profile["inner_glow"]) * 1000), round(float(profile["outer_glow"]) * 1000),
                         round(float(profile["inner_glow_scale"]) * 100), round(float(profile["outer_glow_scale"]) * 100))
    half = sprite.shape[0] // 2
    for x, y, _radius, color, _alpha in dot_geometry(profile, values):
        cx, cy = round(x), round(y)
        left, top = max(0, cx - half), max(0, cy - half)
        right, bottom = min(width, cx - half + sprite.shape[1]), min(height, cy - half + sprite.shape[0])
        if left >= right or top >= bottom:
            continue
        sx, sy = left - (cx - half), top - (cy - half)
        patch = sprite[sy:sy + bottom - top, sx:sx + right - left]
        frame[top:bottom, left:right] += patch * np.asarray(color, np.float32)
    return np.clip(frame, 0, 255).astype(np.uint8)


def robust_normalize(spectrum: np.ndarray) -> np.ndarray:
    spectrum = np.asarray(spectrum, np.float32)
    low = np.percentile(spectrum, 20, axis=0); high = np.percentile(spectrum, 95, axis=0)
    return np.clip((spectrum - low) / np.maximum(high - low, 1e-5), 0, 1).astype(np.float32)
