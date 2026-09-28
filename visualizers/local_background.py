from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class LocalMetrics:
    mean_luminance: float
    median_luminance: float
    p10: float
    p90: float
    local_contrast: float
    highlight_ratio: float
    dark_ratio: float
    texture_density: float
    difficulty: float


def waveform_roi(profile: dict, width: int, height: int, margin: int | None = None) -> tuple[int, int, int, int]:
    """Return the waveform-only analysis region without changing render geometry."""
    scale = min(width / 960.0, height / 160.0)
    pad = max(3, int(round((margin if margin is not None else 10) * scale)))
    x0 = int(np.floor(float(profile["x_position"]) - pad))
    x1 = int(np.ceil(float(profile["x_position"]) + float(profile["active_width"]) + pad))
    maximum_rise = (int(profile["amplitude_ceiling"]) - 1) * float(profile["vertical_gap"])
    y0 = int(np.floor(float(profile["y_position"]) - maximum_rise - pad))
    y1 = int(np.ceil(float(profile["y_position"]) + float(profile["dot_diameter"]) / 2 + pad))
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def analyze_local_background(frame: np.ndarray, roi: tuple[int, int, int, int]) -> LocalMetrics:
    """Measure a small downsampled ROI. Input may be RGB/BGR or grayscale."""
    image = np.asarray(frame)
    x0, y0, x1, y1 = roi
    crop = image[y0:y1, x0:x1]
    if not crop.size:
        crop = image
    if crop.ndim == 3:
        # Channel order has negligible impact on visibility; use perceptual weights
        # symmetrically enough to accept both OpenCV BGR and application RGB frames.
        rgb = crop[..., :3].astype(np.float32) / 255.0
        high = np.max(rgb, axis=2); low = np.min(rgb, axis=2)
        luminance = .50 * np.mean(rgb, axis=2) + .50 * high
        luminance = .85 * luminance + .15 * low
    else:
        luminance = crop.astype(np.float32) / 255.0
    target_width = min(160, max(16, luminance.shape[1]))
    target_height = min(64, max(8, luminance.shape[0]))
    small = cv2.resize(luminance, (target_width, target_height), interpolation=cv2.INTER_AREA)
    mean, median = float(np.mean(small)), float(np.median(small))
    p10, p90 = (float(v) for v in np.percentile(small, (10, 90)))
    contrast = float(np.clip(p90 - p10, 0, 1))
    highlight = float(np.mean(small >= .82)); dark = float(np.mean(small <= .18))
    gx = cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx * gx + gy * gy)
    texture = float(np.clip(np.mean(magnitude > .18) * 1.7 + np.mean(magnitude) * .35, 0, 1))
    bright = float(np.clip((median - .28) / .60, 0, 1))
    difficulty = float(np.clip(.48 * bright + .20 * contrast + .20 * texture + .22 * highlight - .08 * dark, 0, 1))
    return LocalMetrics(mean, median, p10, p90, contrast, highlight, dark, texture, difficulty)


def adaptation_from_metrics(metrics: LocalMetrics) -> dict[str, float]:
    difficulty = metrics.difficulty
    bright = float(np.clip((metrics.median_luminance - .38) / .52, 0, 1))
    texture = metrics.texture_density
    return {
        "difficulty": difficulty,
        "underlay_alpha": float(np.clip(.04 + .27 * difficulty + .07 * texture, .0, .38)),
        "underlay_scale": float(.55 + .95 * difficulty),
        "core_alpha_multiplier": float(1.0 + .20 * difficulty + .07 * texture),
        "core_brightness_multiplier": float(np.clip(1.08 - .24 * bright + .08 * (1 - bright), .80, 1.16)),
        "core_saturation_multiplier": float(1.0 + .18 * bright + .06 * texture),
        "glow_multiplier": float(np.clip(1.10 - .48 * bright - .16 * texture, .50, 1.15)),
    }


def smooth_adaptation(previous: dict[str, float] | None, current: dict[str, float], alpha: float = .16) -> dict[str, float]:
    if previous is None:
        return dict(current)
    return {key: float(previous.get(key, value) + alpha * (value - previous.get(key, value))) for key, value in current.items()}


def derive_underlay_color(stops: list, theme: str = "CUSTOM") -> tuple[int, int, int]:
    presets = {
        "NEON": (55, 14, 64), "WARM": (67, 42, 24), "ELEGANT": (62, 20, 38),
        "SOFT": (58, 50, 65), "ENERGETIC": (30, 28, 70), "MONO": (48, 48, 52),
    }
    if theme.upper() in presets:
        return presets[theme.upper()]
    colors = []
    for _position, value in stops:
        text = str(value).lstrip("#")
        if len(text) == 6:
            colors.append(np.asarray([int(text[i:i + 2], 16) for i in (0, 2, 4)], np.float32))
    if not colors:
        return presets["MONO"]
    darkest = min(colors, key=lambda color: float(.2126 * color[0] + .7152 * color[1] + .0722 * color[2]))
    # Preserve hue while producing a safe colored shadow; never collapse to fixed black.
    return tuple(int(v) for v in np.clip(darkest * .34 + np.mean(darkest) * .06, 18, 82))
