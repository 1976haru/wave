from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


# Matches the lower-third placement used by the real-world composition checks.
DEFAULT_OVERLAY_RECT = (70 / 1920, 850 / 1080, 960 / 1920, 160 / 1080)
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _read_image(path: Path) -> np.ndarray | None:
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except (OSError, ValueError):
        return None


def _crop_overlay(frame: np.ndarray, rect=DEFAULT_OVERLAY_RECT) -> np.ndarray:
    height, width = frame.shape[:2]
    nx, ny, nw, nh = (float(value) for value in rect)
    x0 = int(np.clip(round(nx * width), 0, max(0, width - 1)))
    y0 = int(np.clip(round(ny * height), 0, max(0, height - 1)))
    x1 = int(np.clip(round((nx + nw) * width), x0 + 1, width))
    y1 = int(np.clip(round((ny + nh) * height), y0 + 1, height))
    return frame[y0:y1, x0:x1]


class LocalBackgroundSource:
    """Read-only image/video source for local waveform contrast analysis."""

    def __init__(self, path: str | Path | None, rect=DEFAULT_OVERLAY_RECT):
        self.path = Path(path) if path else None
        self.rect = tuple(rect)
        self.capture = None
        self.image = None
        self.last_frame_index = -1
        self.fps = 24.0
        if not self.path or not self.path.is_file():
            return
        if self.path.suffix.lower() in VIDEO_SUFFIXES:
            self.capture = cv2.VideoCapture(str(self.path))
            measured = float(self.capture.get(cv2.CAP_PROP_FPS)) if self.capture.isOpened() else 0.0
            self.fps = measured if measured > 0 else 24.0
            if not self.capture.isOpened():
                self.capture.release(); self.capture = None
        else:
            self.image = _read_image(self.path)

    @property
    def available(self) -> bool:
        return self.image is not None or self.capture is not None

    def frame(self, seconds: float, width: int, height: int) -> np.ndarray | None:
        source = self.image
        if self.capture is not None:
            wanted = max(0, int(round(float(seconds) * self.fps)))
            if wanted != self.last_frame_index + 1:
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, wanted)
            ok, source = self.capture.read()
            if not ok:
                return None
            self.last_frame_index = wanted
        if source is None:
            return None
        crop = _crop_overlay(source, self.rect)
        return cv2.resize(crop, (int(width), int(height)), interpolation=cv2.INTER_AREA)

    def close(self) -> None:
        if self.capture is not None:
            self.capture.release(); self.capture = None


def source_from_template(template: dict) -> LocalBackgroundSource | None:
    universal = template.get("universal_visualizer", {})
    if not universal.get("local_adapt", True):
        return None
    source = LocalBackgroundSource(template.get("_local_background_source"), template.get("_local_background_rect", DEFAULT_OVERLAY_RECT))
    return source if source.available else None
