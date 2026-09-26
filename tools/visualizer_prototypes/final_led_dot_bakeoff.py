from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audio.analyzer import AnalysisSettings, analyze_file
from core.ffmpeg import resolve_ffmpeg


DEFAULT_OUTPUT = ROOT / "validation_results/final_led_dot_bakeoff"
# OpenCV frames are BGR. These values correspond to the requested RGB hex
# palette: FF3EB5, E44AFF, A658FF and 55D8FF.
PINK = (181, 62, 255)
MAGENTA = (255, 74, 228)
PURPLE = (255, 88, 166)
CYAN = (255, 216, 85)


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    bands: int
    active_width: int
    diameter: float
    x_gap: float
    y_gap: float
    attack: float
    release: float
    neighbor_smoothing: int
    compression: float
    threshold: float
    inner_alpha: float
    outer_alpha: float
    inner_scale: float
    outer_scale: float
    cyan_share: float
    description: str


STYLES = (
    Style("A", "R1 PURE", 28, 330, 3.4, 12.2, 5.6, .48, .82, 1, .67, .105, .18, .045, 1.65, 2.55, .07,
          "Reference fidelity: compact pink LED spectrum, short tail and restrained glow."),
    Style("B", "R1 + SOFT DOT", 28, 340, 3.8, 12.6, 5.8, .43, .86, 1, .66, .095, .25, .075, 1.85, 3.0, .08,
          "R1 structure with rounder antialiased cores and a softer two-stage halo."),
    Style("C", "R1 + TOKYO COLOR", 30, 360, 3.8, 12.4, 5.8, .45, .85, 1, .65, .095, .24, .065, 1.8, 2.9, .15,
          "Compact R1/R2 geometry with pink-magenta-purple and restrained cyan Tokyo colour."),
    Style("D", "SOFT DYNAMIC", 30, 405, 4.0, 14.0, 6.0, .34, .91, 2, .62, .085, .28, .085, 1.95, 3.3, .10,
          "Wider emotional candidate with smoother transitions, lilac emphasis and longer release."),
    Style("E", "CLUB CHILL", 26, 350, 3.6, 14.0, 5.7, .62, .84, 1, .69, .11, .23, .075, 1.7, 2.8, .18,
          "Sharper, faster Tokyo Chill Rap response with stronger pink/cyan contrast."),
)


def font(size: int, bold: bool = False):
    names = ("segoeuib.ttf", "malgunbd.ttf") if bold else ("segoeui.ttf", "malgun.ttf")
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def log_bands(values: np.ndarray, count: int) -> np.ndarray:
    source = np.asarray(values, np.float32)
    # The analyzer output is already perceptual; logarithmic sampling here
    # compresses the high-frequency tail without inventing peaks.
    positions = np.expm1(np.linspace(0, math.log(len(source)), count))
    positions *= (len(source) - 1) / max(1e-6, positions[-1])
    return np.interp(positions, np.arange(len(source)), source).astype(np.float32)


def smooth_neighbors(values: np.ndarray, passes: int) -> np.ndarray:
    result = values.copy()
    for _ in range(passes):
        result = np.convolve(np.pad(result, (1, 1), mode="edge"), (.18, .64, .18), mode="valid")
    return result.astype(np.float32)


def palette(style: Style, position: float, level: float) -> tuple[int, int, int]:
    # Ratios remain pink/magenta dominant. Cyan is confined to the last
    # 7–18 percent and slightly promoted only at high LED levels.
    cyan_start = 1.0 - style.cyan_share
    if position < .58:
        a, b, mix = PINK, MAGENTA, position / .58
    elif position < cyan_start:
        a, b, mix = MAGENTA, PURPLE, (position - .58) / max(.01, cyan_start - .58)
    else:
        a, b, mix = PURPLE, CYAN, (position - cyan_start) / max(.01, style.cyan_share)
    mix = float(np.clip(mix, 0, 1))
    color = np.asarray(a) * (1 - mix) + np.asarray(b) * mix
    color = color * (.82 + .18 * level)
    return tuple(int(np.clip(v, 0, 255)) for v in color)


def geometry(style: Style, values: np.ndarray) -> list[tuple[float, float, float, tuple[int, int, int], float]]:
    data = smooth_neighbors(log_bands(values, style.bands), style.neighbor_smoothing)
    data = np.power(np.clip(data, 0, 1), style.compression)
    # Natural spectral roll-off shortens the tail; no Gaussian mound or
    # fabricated skyline is applied.
    rolloff = np.linspace(1.0, .62, style.bands, dtype=np.float32)
    data *= rolloff
    x0 = 70.0
    xs = np.linspace(x0, x0 + style.active_width, style.bands)
    base = 139.0
    dots = []
    for index, (x, energy) in enumerate(zip(xs, data)):
        if energy < style.threshold:
            continue
        count = int(np.clip(1 + (energy - style.threshold) / (1 - style.threshold) * 15, 1, 16))
        for row in range(count):
            level = row / max(1, count - 1)
            dots.append((float(x), base - row * style.y_gap, style.diameter / 2,
                         palette(style, index / max(1, style.bands - 1), level), .92 + .08 * level))
    return dots


def render(style: Style, values: np.ndarray, width=960, height=160) -> np.ndarray:
    scale = 3
    core = np.zeros((height * scale, width * scale, 3), np.float32)
    inner = np.zeros_like(core)
    outer = np.zeros_like(core)
    for x, y, radius, color, alpha in geometry(style, values):
        center = (round(x * scale), round(y * scale)); rgb = tuple(float(c) for c in color)
        cv2.circle(outer, center, max(1, round(radius * style.outer_scale * scale)), rgb, -1, cv2.LINE_AA)
        cv2.circle(inner, center, max(1, round(radius * style.inner_scale * scale)), rgb, -1, cv2.LINE_AA)
        cv2.circle(core, center, max(1, round(radius * scale)), tuple(c * alpha for c in rgb), -1, cv2.LINE_AA)
    if style.outer_alpha:
        outer = cv2.GaussianBlur(outer, (0, 0), 2.2 * scale) * style.outer_alpha
    if style.inner_alpha:
        inner = cv2.GaussianBlur(inner, (0, 0), .75 * scale) * style.inner_alpha
    image = np.clip(core + inner + outer, 0, 255).astype(np.uint8)
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def encode(ffmpeg: str, audio: Path, output: Path, features: dict, style: Style, seconds: float, fps=24) -> dict:
    command = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "960x160", "-r", str(fps),
               "-i", "pipe:0", "-i", str(audio), "-t", str(seconds), "-shortest", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    spectrum = np.asarray(features["spectrum"], np.float32)
    state = np.zeros(spectrum.shape[1], np.float32)
    dot_counts = []
    started = time.perf_counter()
    for frame_index in range(int(seconds * fps)):
        target = spectrum[min(frame_index, len(spectrum) - 1)]
        coefficient = style.attack if np.mean(target) > np.mean(state) else (1 - style.release)
        state += (target - state) * coefficient
        frame = render(style, state)
        dot_counts.append(len(geometry(style, state)))
        process.stdin.write(frame.tobytes())
    process.stdin.close()
    if process.wait():
        raise RuntimeError(f"ffmpeg failed: {style.key}")
    elapsed = time.perf_counter() - started
    return {"average_fps": int(seconds * fps) / elapsed, "dot_count_median": float(np.median(dot_counts)),
            "dot_count_p90": float(np.percentile(dot_counts, 90))}


def compose(ffmpeg: str, wave: Path, background: Path, output: Path, seconds: float, opacity: float) -> None:
    graph = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=rgb24[bg];"
             "color=c=black:s=1920x1080:r=24[c];[1:v]scale=960:160[w];"
             "[c][w]overlay=x=230:y=825:shortest=1[wf];"
             f"[bg][wf]blend=all_mode=screen:all_opacity={opacity:.2f}[out]")
    subprocess.run([ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background), "-i", str(wave),
                    "-filter_complex", graph, "-map", "[out]", "-map", "1:a?", "-t", str(seconds), "-r", "24",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(output)], check=True)


def frame(path: Path, timestamp: float) -> Image.Image:
    capture = cv2.VideoCapture(str(path)); capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000); ok, value = capture.read(); capture.release()
    if not ok:
        raise RuntimeError(path)
    return Image.fromarray(cv2.cvtColor(value, cv2.COLOR_BGR2RGB))


def sheet(paths: list[Path], target: Path, timestamp: float, subtitle: str) -> None:
    canvas = Image.new("RGB", (1600, 310), "#080b12"); draw = ImageDraw.Draw(canvas)
    for index, (style, path) in enumerate(zip(STYLES, paths)):
        x = index * 320; image = frame(path, timestamp).resize((320, 180), Image.Resampling.LANCZOS); canvas.paste(image, (x, 0))
        draw.rectangle((x, 180, x + 320, 310), fill="#10151f")
        draw.text((x + 12, 194), f"{style.key}  {style.name}", font=font(20, True), fill="#f5f7ff")
        draw.text((x + 12, 225), subtitle, font=font(14), fill="#9cabc3")
        draw.text((x + 12, 250), f"{style.bands} bands / {style.active_width}px", font=font(13), fill="#d8a9ef")
    canvas.save(target)


def reference_diagram() -> Image.Image:
    canvas = Image.new("RGB", (480, 270), "#080b12"); draw = ImageDraw.Draw(canvas)
    draw.text((20, 18), "REFERENCE STRUCTURE", font=font(22, True), fill="#f4f7ff")
    draw.text((20, 48), "compact / round LED / short tail / no baseline", font=font(14), fill="#9daac0")
    synthetic = np.array([.28, .35, .55, .88, .72, .52, .66, .46, .34, .25, .20, .16, .11, .08], np.float32)
    for index, energy in enumerate(synthetic):
        x = 38 + index * 24; count = max(1, int(energy * 10))
        color = palette(STYLES[2], index / (len(synthetic)-1), .7)
        for row in range(count):
            draw.ellipse((x-3, 234-row*14-3, x+3, 234-row*14+3), fill=color[::-1])
    return canvas


def compare_sheet(paths: list[Path], target: Path, timestamp: float) -> None:
    canvas = Image.new("RGB", (1440, 650), "#080b12"); draw = ImageDraw.Draw(canvas); canvas.paste(reference_diagram(), (0, 0))
    positions = [(480, 0), (960, 0), (0, 325), (480, 325), (960, 325)]
    for style, path, (x, y) in zip(STYLES, paths, positions):
        image = frame(path, timestamp).resize((480, 270), Image.Resampling.LANCZOS); canvas.paste(image, (x, y))
        draw.rectangle((x, y + 270, x + 480, y + 325), fill="#10151f")
        draw.text((x + 12, y + 282), f"{style.key}  {style.name}", font=font(20, True), fill="#f5f7ff")
    canvas.save(target)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--seconds", type=float, default=24); parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT); args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True); ffmpeg = resolve_ffmpeg(None)
    audio = ROOT / "validation_results/v0839_chill_girl_vibes/validation_fixture_30s.wav"
    features, _ = analyze_file(audio, AnalysisSettings(fps=24, bands=64), logger=lambda *_: None)
    # Calibrate every analyzer band against the same full-fixture robust
    # range. This preserves real FFT motion while preventing the naturally
    # tiny high-frequency magnitudes from collapsing the designed tail.
    spectrum = np.asarray(features["spectrum"], np.float32)
    low = np.percentile(spectrum, 20, axis=0)
    high = np.percentile(spectrum, 95, axis=0)
    features["spectrum"] = np.clip((spectrum - low) / np.maximum(high - low, 1e-5), 0, 1).astype(np.float32)
    waves, mids, darks, report = [], [], [], []
    for style in STYLES:
        wave = args.output / f"{style.key}_{style.name.replace(' + ', '_').replace(' ', '_')}.mp4"
        # Required filenames use a stable explicit mapping below.
        required = {"A": "A_R1_PURE.mp4", "B": "B_R1_SOFT_DOT.mp4", "C": "C_R1_TOKYO_COLOR.mp4", "D": "D_SOFT_DYNAMIC.mp4", "E": "E_CLUB_CHILL.mp4"}[style.key]
        wave = args.output / required
        metrics = encode(ffmpeg, audio, wave, features, style, args.seconds); waves.append(wave)
        mid, dark = args.output / f"{style.key}_mid.mp4", args.output / f"{style.key}_dark.mp4"
        compose(ffmpeg, wave, ROOT / "sample_assets/background/v0833_cafe_window_fixture.png", mid, args.seconds, .90)
        compose(ffmpeg, wave, ROOT / "sample_assets/background/v0830_tokyo_night_fixture.png", dark, args.seconds, .80)
        mids.append(mid); darks.append(dark); report.append({**asdict(style), **metrics}); print(style.key, style.name, flush=True)
    timestamp = min(17.0, args.seconds * .72)
    sheet(waves, args.output / "final_5style_wave_only.png", timestamp, "Wave only")
    sheet(mids, args.output / "final_5style_mid.png", timestamp, "Mid-tone composition")
    sheet(darks, args.output / "final_5style_dark.png", timestamp, "Dark composition")
    compare_sheet(waves, args.output / "final_5style_reference_compare.png", timestamp)
    payload = {"version": "0.8.3.9", "audio": str(audio), "seconds": args.seconds, "fps": 24, "styles": report,
               "decision": "USER SELECTION REQUIRED", "production_renderer_modified": False}
    (args.output / "bakeoff_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["FINAL LED DOT BAKE-OFF", "", "Common engine: 64-band analysis with per-band p20/p95 robust normalization -> 24-32 logarithmic display bands; discrete round LEDs; no baseline/top contour.", ""]
    for item in report:
        lines += [f"{item['key']} - {item['name']}", f"  active width: {item['active_width']}px", f"  bands: {item['bands']}",
                  f"  dot diameter: {item['diameter']}px", f"  gaps: x={item['x_gap']} / y={item['y_gap']}px",
                  f"  glow: inner {item['inner_alpha']:.3f}, outer {item['outer_alpha']:.3f}", f"  cyan share: {item['cyan_share']:.0%}",
                  f"  median/p90 dots: {item['dot_count_median']:.0f}/{item['dot_count_p90']:.0f}", f"  render fps: {item['average_fps']:.1f}",
                  f"  {item['description']}", ""]
    lines += ["Winner: USER SELECTION REQUIRED", "Production renderer: NOT MODIFIED", "VERSION: 0.8.3.9"]
    (args.output / "bakeoff_report.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
