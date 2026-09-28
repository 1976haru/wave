from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "validation_results" / "v0841_local_background_adapt"
sys.path.insert(0, str(ROOT))

from animation.engine import AnimationEngine
from audio.analyzer import AnalysisSettings, analyze_file
from core.ffmpeg import resolve_ffmpeg
from template_system import load_template
from visualizers.families.soft_round_led import SoftRoundLEDRenderer

FPS = 24
DURATION = 28
FRAMES = FPS * DURATION
CHILL_VIDEO = ROOT / "validation_results/v0840_real_world_validation/_chill_background_28s.mp4"
CHILL_AUDIO = ROOT / "validation_results/v0840_real_world_validation/_chill_actual_28s.wav"
CALM_AUDIO = ROOT / "validation_results/v0840_real_world_validation/_calm_actual_28s.wav"
CALM_IMAGE = Path(r"D:\02_시니어 채널\1113_첫눈이 생각나는 감성 올드팝\음원커버 및 썸네일\썸네일 1.png")

CASES = [
    ("01_CHILL_STANDARD_BEFORE", "chill", "NEON", "STANDARD", False),
    ("02_CHILL_STANDARD_LOCAL_ADAPT", "chill", "NEON", "STANDARD", True),
    ("03_CHILL_DYNAMIC_BEFORE", "chill", "NEON", "DYNAMIC", False),
    ("04_CHILL_DYNAMIC_LOCAL_ADAPT", "chill", "NEON", "DYNAMIC", True),
    ("05_CALM_WARM_BEFORE", "calm", "WARM", "CALM", False),
    ("06_CALM_WARM_LOCAL_ADAPT", "calm", "WARM", "CALM", True),
    ("07_CALM_ELEGANT_BEFORE", "calm", "ELEGANT", "CALM", False),
    ("08_CALM_ELEGANT_LOCAL_ADAPT", "calm", "ELEGANT", "CALM", True),
]


def cover(image: np.ndarray, width=1920, height=1080) -> np.ndarray:
    scale = max(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(image, (round(image.shape[1] * scale), round(image.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    x, y = (resized.shape[1] - width) // 2, (resized.shape[0] - height) // 2
    return resized[y:y + height, x:x + width]


def template_for(theme: str, intensity: str, enabled: bool) -> dict:
    template = load_template(ROOT / "templates/00_universal_soft_round_led.json")
    template["universal_visualizer"].update({"theme": theme, "intensity": intensity, "width": "STANDARD",
                                               "position": "LEFT", "local_adapt": enabled, "auto_adapt": True})
    return template


def composite(background: np.ndarray, overlay: np.ndarray, x=70, y=850) -> tuple[np.ndarray, float]:
    result = background.copy(); rgb = overlay[..., :3].astype(np.float32); alpha = overlay[..., 3:4].astype(np.float32) / 255
    roi = result[y:y + overlay.shape[0], x:x + overlay.shape[1]].astype(np.float32)
    # Renderer RGB is premultiplied; retain dark theme-aware underlay correctly.
    mixed = roi * (1 - alpha) + rgb
    result[y:y + overlay.shape[0], x:x + overlay.shape[1]] = np.clip(mixed, 0, 255).astype(np.uint8)
    mask = overlay[..., 3] > 20
    # Perceptual Lab distance captures the darker, more saturated adaptive core
    # better than raw RGB brightness difference on near-white backgrounds.
    original_lab = cv2.cvtColor(np.clip(roi, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    mixed_lab = cv2.cvtColor(np.clip(mixed, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    delta = np.linalg.norm(mixed_lab - original_lab, axis=2)
    presence = float(np.mean(delta[mask])) if np.any(mask) else 0.0
    return result, presence


def encoder(ffmpeg: str, target: Path, audio: Path) -> subprocess.Popen:
    command = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1920x1080", "-r", str(FPS),
               "-i", "pipe:0", "-i", str(audio), "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(target)]
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def render_group(kind: str, background_source, audio: Path, cases: list, ffmpeg: str) -> dict:
    features, _ = analyze_file(audio, AnalysisSettings(fps=FPS, bands=64), OUT / "_analysis_cache")
    prepared = []
    for name, _kind, theme, intensity, enabled in cases:
        template = template_for(theme, intensity, enabled)
        prepared.append({"name": name, "template": template, "engine": AnimationEngine(features, copy.deepcopy(template)),
                         "renderer": SoftRoundLEDRenderer(), "encoder": encoder(ffmpeg, OUT / f"{name}.mp4", audio),
                         "presence": [], "representative": None})
    capture = cv2.VideoCapture(str(background_source)) if kind == "chill" else None
    static = None if capture else cover(cv2.imdecode(np.fromfile(background_source, np.uint8), cv2.IMREAD_COLOR))
    started = time.perf_counter()
    for index in range(FRAMES):
        if capture:
            ok, background = capture.read()
            if not ok:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0); ok, background = capture.read()
            background = cover(background)
        else:
            background = static
        local_background = background[850:1010, 70:1030]
        for item in prepared:
            state = item["engine"].sample(index / FPS); state["background_frame"] = local_background
            overlay = item["renderer"].render_rgba(960, 160, state, item["template"])
            composed, presence = composite(background, overlay); item["presence"].append(presence)
            item["encoder"].stdin.write(memoryview(composed))
            if index == FRAMES // 2:
                item["representative"] = composed.copy()
    if capture: capture.release()
    elapsed = time.perf_counter() - started
    metrics = {}
    for item in prepared:
        item["encoder"].stdin.close(); code = item["encoder"].wait()
        if code: raise RuntimeError(f"encoder failed: {item['name']}")
        cv2.imwrite(str(OUT / f"_{item['name']}.png"), item["representative"])
        metrics[item["name"]] = {"mean_presence": round(float(np.mean(item["presence"])), 3),
                                  "minimum_presence": round(float(np.min(item["presence"])), 3),
                                  "render_fps": round(FRAMES * len(prepared) / elapsed, 2)}
    return metrics


def label(image: np.ndarray, text: str) -> np.ndarray:
    tile = cv2.resize(image, (960, 540), interpolation=cv2.INTER_AREA)
    cv2.rectangle(tile, (0, 0), (960, 54), (10, 12, 18), -1)
    cv2.putText(tile, text, (18, 37), cv2.FONT_HERSHEY_SIMPLEX, .72, (245, 245, 245), 2, cv2.LINE_AA)
    return tile


def pair(before: str, after: str) -> np.ndarray:
    left = label(cv2.imread(str(OUT / f"_{before}.png")), "BEFORE | " + before)
    right = label(cv2.imread(str(OUT / f"_{after}.png")), "AFTER | " + after)
    return np.hstack((left, right))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); ffmpeg = resolve_ffmpeg(None)
    if not ffmpeg: raise RuntimeError("FFmpeg is required")
    metrics = {}
    metrics.update(render_group("chill", CHILL_VIDEO, CHILL_AUDIO, [case for case in CASES if case[1] == "chill"], ffmpeg))
    metrics.update(render_group("calm", CALM_IMAGE, CALM_AUDIO, [case for case in CASES if case[1] == "calm"], ffmpeg))
    chill = np.vstack((pair(CASES[0][0], CASES[1][0]), pair(CASES[2][0], CASES[3][0])))
    calm = np.vstack((pair(CASES[4][0], CASES[5][0]), pair(CASES[6][0], CASES[7][0])))
    cv2.imwrite(str(OUT / "local_adapt_chill_ab.png"), chill)
    cv2.imwrite(str(OUT / "local_adapt_calm_ab.png"), calm)
    cv2.imwrite(str(OUT / "local_adapt_all_ab.png"), np.vstack((chill, calm)))
    before = cv2.imread(str(OUT / f"_{CASES[6][0]}.png"))[820:1030, 40:1060]
    after = cv2.imread(str(OUT / f"_{CASES[7][0]}.png"))[820:1030, 40:1060]
    crop = np.hstack((label(before, "BEFORE · 3.5x"), label(after, "AFTER · 3.5x")))
    cv2.imwrite(str(OUT / "local_adapt_wave_crop_ab.png"), crop)
    improvements = {}
    for before_case, after_case in zip(CASES[::2], CASES[1::2]):
        before_value = metrics[before_case[0]]["mean_presence"]; after_value = metrics[after_case[0]]["mean_presence"]
        improvements[after_case[0]] = round((after_value / max(before_value, 1e-6) - 1) * 100, 1)
    payload = {"version": "0.8.4.1", "metrics": metrics, "presence_improvement_percent": improvements}
    (OUT / "validation_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "Music Wave Studio v0.8.4.1 - LOCAL BACKGROUND ADAPT VALIDATION",
        "", "Geometry/FFT/motion changed: NO", "Tokyo Signature work started: NO",
        "Analysis: waveform-local ROI luminance/contrast/highlight/texture + temporal EMA",
        "Underlay: theme-derived dot-local contrast halo (no black outline/backplate)", "",
    ]
    for name, values in metrics.items():
        report.append(f"{name}: presence={values['mean_presence']:.3f}, min={values['minimum_presence']:.3f}, fps={values['render_fps']:.2f}")
    report.extend(["", "Presence improvement:"])
    report.extend(f"{name}: {value:+.1f}%" for name, value in improvements.items())
    report.extend(["", "Visual approval: USER REVIEW REQUIRED"])
    (OUT / "validation_report.txt").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
