from __future__ import annotations

import math
from functools import lru_cache

import cv2
import numpy as np

from visualizers.local_background import adaptation_from_metrics, analyze_local_background, derive_underlay_color, smooth_adaptation

SUPPORTED_PARAMETERS = ("shape_id", "shape_size", "position_x", "position_y", "movement", "response_strength", "color_mode", "color_a", "color_b", "opacity", "stroke_style", "glow_level", "local_adapt")

SHAPE_IDS = (
    "MORNING_HALO", "PEARL_HALO", "TWIN_HALO", "BREATHING_RING", "SUNRISE_ARC",
    "SOFT_OVAL", "VERTICAL_OVAL", "ROUND_SQUARE", "PEARL_SQUARE", "SOFT_DIAMOND",
    "HEART_WHISPER", "PEARL_HEART", "SOFT_CAPSULE", "CLOUD_LOOP", "PETAL_LOOP",
    "FLOWER_HALO", "RIBBON_ORBIT", "STEREO_ORBIT", "DOTTED_ORBIT", "CAFE_FRAME",
)

MORNING_COLORS = {
    "MORNING_WHITE": "#FFF8EC", "WARM_CREAM": "#FFE8C7", "SOFT_PEACH": "#FFCDB6",
    "BLUSH_PINK": "#F6B9C8", "DUSTY_ROSE": "#DFA4B4", "PALE_GOLD": "#F4D58D",
    "SOFT_LAVENDER": "#C9B8E8", "SKY_MIST": "#B9D9EA", "SAGE_MIST": "#BCD5C0",
    "PURE_WHITE": "#FFFFFF",
}

MOVEMENT_LIMIT = {"CALM": .045, "STANDARD": .065, "LIVELY": .095}
STROKE_SCALE = {"THIN": .72, "DEFAULT": 1.0, "THICK": 1.38}
GLOW = {"NONE": (0.0, 0.0), "SUBTLE": (.16, 2.2), "DEFAULT": (.25, 3.2)}
DOT_SHAPES = {"PEARL_HALO", "PEARL_SQUARE", "PEARL_HEART"}


def _hex(value):
    text = str(value or "#FFFFFF").lstrip("#")
    if len(text) != 6:
        text = "FFFFFF"
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def _superellipse(theta, exponent=4.0):
    c, s = np.cos(theta), np.sin(theta)
    power = 2.0 / exponent
    return np.column_stack((np.sign(c) * np.abs(c) ** power, np.sign(s) * np.abs(s) ** power))


@lru_cache(maxsize=96)
def normalized_path(shape_id: str, count: int) -> np.ndarray:
    """Return a tiny immutable-style normalized perimeter array in [-1, 1]."""
    shape_id = str(shape_id).upper()
    count = int(np.clip(count, 48, 320))
    closed = shape_id != "SUNRISE_ARC"
    if shape_id == "SUNRISE_ARC":
        theta = np.linspace(math.radians(-70), math.radians(230), count)
    else:
        theta = np.linspace(-math.pi / 2, math.pi * 1.5, count, endpoint=False)
    if shape_id in {"ROUND_SQUARE", "PEARL_SQUARE"}:
        points = _superellipse(theta, 4.2)
    elif shape_id == "SOFT_DIAMOND":
        base = _superellipse(theta, 3.2)
        angle = math.pi / 4
        points = base @ np.array([[math.cos(angle), math.sin(angle)], [-math.sin(angle), math.cos(angle)]], np.float32)
        points *= .82
    elif shape_id in {"HEART_WHISPER", "PEARL_HEART"}:
        t = np.linspace(0, 2 * math.pi, count, endpoint=False)
        x = 16 * np.sin(t) ** 3 / 17
        y = -(13 * np.cos(t) - 5 * np.cos(2*t) - 2 * np.cos(3*t) - np.cos(4*t)) / 17
        points = np.column_stack((x, y)); points[:, 1] += .08
    elif shape_id == "SOFT_CAPSULE":
        points = _superellipse(theta, 3.2); points[:, 0] *= 1.0; points[:, 1] *= .52
    else:
        lobes = {"CLOUD_LOOP": (5, .075), "PETAL_LOOP": (4, .13), "FLOWER_HALO": (6, .055)}
        radius = np.ones_like(theta)
        if shape_id in lobes:
            frequency, amount = lobes[shape_id]; radius += amount * np.cos(frequency * theta)
        points = np.column_stack((np.cos(theta) * radius, np.sin(theta) * radius))
        if shape_id in {"SOFT_OVAL", "DOTTED_ORBIT", "RIBBON_ORBIT", "STEREO_ORBIT"}: points[:, 1] *= .68
        if shape_id == "VERTICAL_OVAL": points[:, 0] *= .68
        if shape_id == "CAFE_FRAME": points = _superellipse(theta, 4.2); points[:, 1] *= .48
    points = np.asarray(points, np.float32)
    points.setflags(write=False)
    return points


def _quality_count(template, dotted=False):
    quality = str(template.get("_quality", "BALANCED")).upper()
    count = {"PREVIEW": 128, "BALANCED": 208, "NORMAL": 208, "QUALITY": 288, "HIGH": 288}.get(quality, 208)
    return min(count, 160) if dotted else count


def resolve_profile(template, width, height):
    s = template.get("morning_shape", template)
    shape_id = str(s.get("shape_id", "MORNING_HALO")).upper()
    size = float(np.clip(s.get("shape_size", 1.0), .5, 2.0))
    scale = min(width, height) * .255 * size
    aspect = width / max(height, 1)
    center = np.array([width * float(np.clip(s.get("position_x", .5), .05, .95)), height * float(np.clip(s.get("position_y", .5), .05, .95))], np.float32)
    # Overlay canvases are shallow; preserve a useful full-frame-equivalent circle.
    if aspect > 3.0: scale = height * .38 * size
    movement = str(s.get("movement", "CALM")).upper()
    return {"settings": s, "shape_id": shape_id, "size": size, "scale": scale, "center": center,
            "limit": MOVEMENT_LIMIT.get(movement, MOVEMENT_LIMIT["CALM"]), "response": float(np.clip(s.get("response_strength", 1.0), .25, 2.0)),
            "opacity": float(np.clip(s.get("opacity", .88), .4, 1.0)), "local_adapt": bool(s.get("local_adapt", True))}


def shape_geometry(width: int, height: int, state: dict, template: dict) -> dict:
    p = resolve_profile(template, width, height); sid = p["shape_id"]; dotted = sid in DOT_SHAPES
    count = _quality_count(template, dotted); base = np.array(normalized_path(sid, count), copy=True)
    # The path tangent defines a robust outward normal for all parametric contours.
    previous = np.roll(base, 1, axis=0); following = np.roll(base, -1, axis=0)
    tangent = following - previous; normal = np.column_stack((tangent[:, 1], -tangent[:, 0]))
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-6)
    outward = np.sum(normal * base, axis=1) < 0; normal[outward] *= -1
    values = np.asarray(state.get("values", [0]), np.float32)
    phase = np.linspace(0, 1, count, endpoint=False)
    spectrum = np.interp((phase * 2 % 1) * max(0, len(values)-1), np.arange(len(values)), values)
    spectrum = .5 * (spectrum + spectrum[::-1])
    low_wave = np.convolve(np.pad(spectrum, (4, 4), mode="wrap"), np.ones(9)/9, mode="valid")
    bass = float(state.get("bass", state.get("rms", .3))); mid = float(state.get("mid", .3)); high = float(state.get("high", .2)); onset = float(state.get("onset", 0)); rms = float(state.get("rms", state.get("energy", .3)))
    breathing = (.35*bass + .10*rms - .16)
    ripple = .30*(low_wave-.35)*(.55+.45*mid) + .22*(spectrum-low_wave)*(.45+.55*mid)
    micro = .08*high*np.sin(phase*math.tau*11 + spectrum*2.0) + .05*onset*np.sin(phase*math.tau*3)
    deformation = np.clip((breathing + ripple + micro) * p["response"], -p["limit"], p["limit"])
    if sid == "BREATHING_RING": deformation = np.clip(breathing*p["response"] + ripple*.18, -p["limit"], p["limit"])
    points = p["center"] + (base + normal*deformation[:, None]) * p["scale"]
    if sid == "TWIN_HALO":
        second = p["center"] + (base*.88 + normal*np.roll(deformation, 7)[:, None]*.55) * p["scale"]
    elif sid == "RIBBON_ORBIT":
        second = p["center"] + (base*.94 + normal*np.roll(deformation, count//9)[:, None]*.62) * p["scale"]
    else: second = None
    margin = max(8, int(p["scale"] * (p["limit"] + .08)))
    bounds = (max(0, int(points[:,0].min()-margin)), max(0, int(points[:,1].min()-margin)), min(width, int(points[:,0].max()+margin)), min(height, int(points[:,1].max()+margin)))
    return {"profile": p, "base": base, "points": points.astype(np.float32), "second": None if second is None else second.astype(np.float32), "deformation": deformation, "bounds": bounds, "dotted": dotted}


class MorningShapeRenderer:
    name = "CPU/MORNING_SHAPE"
    def __init__(self): self._adapt = None; self._frame = 0; self.last_local_metrics = None

    def render_rgba(self, width, height, state, template):
        g = shape_geometry(width, height, state, template); p = g["profile"]; s = p["settings"]
        local = {"underlay_alpha":0.0, "core_alpha_multiplier":1.0, "core_brightness_multiplier":1.0, "core_saturation_multiplier":1.0, "glow_multiplier":1.0}
        background = state.get("background_frame")
        if p["local_adapt"] and background is not None:
            image = np.asarray(background)
            if image.shape[:2] != (height, width): image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            if self._frame % 3 == 0 or self._adapt is None:
                metrics = analyze_local_background(image, g["bounds"]); self._adapt = smooth_adaptation(self._adapt, adaptation_from_metrics(metrics)); self.last_local_metrics = metrics
            local = self._adapt
        self._frame += 1
        rgb = np.zeros((height, width, 3), np.float32); alpha = np.zeros((height, width), np.float32)
        color_a = _hex(s.get("color_a", MORNING_COLORS["MORNING_WHITE"])); color_b = _hex(s.get("color_b", MORNING_COLORS["SOFT_PEACH"]))
        gradient = str(s.get("color_mode", "SOLID")).upper() == "GRADIENT"
        stroke = max(1, round(min(width,height)/540*2.0*STROKE_SCALE.get(str(s.get("stroke_style","THIN")).upper(), .72)))
        opacity = p["opacity"] * local["core_alpha_multiplier"]
        under = derive_underlay_color([[0, s.get("color_a", "#FFF8EC")], [1, s.get("color_b", "#FFCDB6")]], "CUSTOM")

        def color_at(index, count):
            mix = index/max(1,count-1) if gradient else 0.0
            color = np.asarray(color_a)*(1-mix)+np.asarray(color_b)*mix
            return np.clip(color*local["core_brightness_multiplier"], 0, 255).tolist()
        def paint_line(points, alpha_scale=1.0, color_offset=0, closed=None, solid_color=None):
            pts = np.round(points).astype(np.int32); closed = (p["shape_id"] != "SUNRISE_ARC") if closed is None else bool(closed)
            for i in range(len(pts)-1 + int(closed)):
                a, b = pts[i%len(pts)], pts[(i+1)%len(pts)]; color = list(solid_color) if solid_color is not None else color_at((i+color_offset)%len(pts), len(pts))
                if local["underlay_alpha"] > 0: cv2.line(rgb, tuple(a), tuple(b), under, stroke+2, cv2.LINE_AA); cv2.line(alpha, tuple(a), tuple(b), local["underlay_alpha"]*255, stroke+2, cv2.LINE_AA)
                cv2.line(rgb, tuple(a), tuple(b), color, stroke, cv2.LINE_AA); cv2.line(alpha, tuple(a), tuple(b), min(255,opacity*alpha_scale*255), stroke, cv2.LINE_AA)
        def paint_dots(points):
            diameter = max(2.0, min(width,height)/540*4.0*STROKE_SCALE.get(str(s.get("stroke_style","THIN")).upper(), .72))
            for i, point in enumerate(points):
                radius = diameter*.5*(.94+.10*float(np.clip(state.get("rms",.3),0,1)))
                cv2.circle(rgb, tuple(np.round(point).astype(int)), max(1,round(radius)), color_at(i,len(points)), -1, cv2.LINE_AA); cv2.circle(alpha, tuple(np.round(point).astype(int)), max(1,round(radius)), min(255,opacity*255), -1, cv2.LINE_AA)
        sid = p["shape_id"]
        if g["dotted"]: paint_dots(g["points"])
        elif sid == "DOTTED_ORBIT":
            for start in range(0,len(g["points"]),4):
                if (start//4)%2: paint_dots(g["points"][start:start+1])
                else: paint_line(g["points"][start:start+3], .9, closed=False)
        elif sid == "STEREO_ORBIT":
            half=len(g["points"])//2;paint_line(g["points"][:half+1],closed=False,solid_color=_hex("#FFCDB6"));paint_line(g["points"][half:],closed=False,solid_color=_hex("#B9D9EA"))
        else:
            paint_line(g["points"])
            if g["second"] is not None: paint_line(g["second"], .58, len(g["points"])//4)
        glow_strength, radius = GLOW.get(str(s.get("glow_level","SUBTLE")).upper(), GLOW["SUBTLE"])
        if glow_strength:
            glow = cv2.GaussianBlur(rgb,(0,0),radius); rgb=np.clip(rgb+glow*glow_strength*local["glow_multiplier"],0,255)
            alpha=np.clip(alpha+cv2.GaussianBlur(alpha,(0,0),radius)*glow_strength*.45,0,255)
        return np.dstack((rgb.astype(np.uint8),alpha.astype(np.uint8)))
