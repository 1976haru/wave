from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audio.analyzer import AnalysisSettings, analyze_file
from core.ffmpeg import resolve_ffmpeg


STYLES = [
    ("01_reference_led_dot", "Reference R1 · LED Dot Spectrum"),
    ("02_true_led_spectrum", "True LED Spectrum"),
    ("03_soft_round_led", "Reference R2 · Soft Round LED"),
    ("04_monstercat_minimal", "Monstercat Minimal"),
    ("05_cava_smooth", "CAVA Smooth Bars"),
    ("06_rounded_neon_bars", "Rounded Neon Bars"),
    ("07_dot_glow_columns", "Dot + Glow Columns"),
    ("08_particle_spectrum", "Particle Spectrum"),
    ("09_minimal_wave_dots", "Minimal Wave Dots"),
    ("10_gradient_dot_spectrum", "Reference R3 · Tokyo Gradient Dots"),
    ("11_soft_equalizer_lights", "Soft Equalizer Lights"),
    ("12_designer_hybrid", "Designer Hybrid"),
]

PALETTES = {
    "pink": [(255, 62, 162), (255, 112, 193), (204, 108, 255)],
    "tokyo": [(255, 66, 164), (189, 105, 255), (66, 217, 255)],
    "cyan": [(42, 107, 255), (65, 213, 255), (145, 237, 255)],
}


def font(size: int):
    for path in (Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\malgun.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def color_at(palette, value):
    value = float(np.clip(value, 0, .9999)); scaled = value * (len(palette) - 1); index = int(scaled); mix = scaled - index
    a = np.asarray(palette[index], np.float32); b = np.asarray(palette[min(index + 1, len(palette) - 1)], np.float32)
    return tuple(int(x) for x in a * (1 - mix) + b * mix)


def bands(values, count, smooth=2):
    source = np.asarray(values, np.float32)
    mapped = np.interp(np.linspace(0, len(source) - 1, count), np.arange(len(source)), source)
    for _ in range(smooth):
        mapped = np.convolve(np.pad(mapped, (2, 2), mode="edge"), [.08, .22, .40, .22, .08], mode="valid")
    return np.clip(mapped, 0, 1)


def glow_dots(frame, dots, blur=5, strength=.28):
    halo = np.zeros_like(frame)
    for x, y, radius, color, alpha in dots:
        cv2.circle(halo, (int(x), int(y)), max(1, int(radius * 1.8)), color, -1, cv2.LINE_AA)
        cv2.circle(frame, (int(x), int(y)), max(1, int(radius)), tuple(int(c * alpha) for c in color), -1, cv2.LINE_AA)
    if blur:
        halo = cv2.GaussianBlur(halo, (0, 0), blur)
        cv2.addWeighted(frame, 1, halo, strength, 0, frame)


def render_style(style: int, values, onset: float, seconds: float, width=960, height=160):
    frame = np.zeros((height, width, 3), np.uint8); base = 135; dots = []
    pink, tokyo, cyan = PALETTES["pink"], PALETTES["tokyo"], PALETTES["cyan"]
    if style == 1:  # faithful compact pink LED reference
        data = bands(values, 30, 1); xs = np.linspace(120, 650, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            rows = 1 + int(value * 8)
            for row in range(rows): dots.append((x, base - row * 8, 2.6, color_at(pink, i / len(data)), .96))
    elif style == 2:  # true LED, discrete level colour
        data = bands(values, 48, 1); xs = np.linspace(70, 890, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            for row in range(1 + int(value * 10)):
                level = row / 10; color = color_at(tokyo, level)
                cv2.rectangle(frame, (int(x - 4), base - row * 9 - 5), (int(x + 4), base - row * 9), color, -1, cv2.LINE_AA)
    elif style == 3:  # round LED with breathing room
        data = bands(values, 34, 2); xs = np.linspace(110, 850, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            for row in range(1 + int(value * 7)):
                dots.append((x, base - row * 10, 3.4, color_at(tokyo, .12 + .75 * i / len(data)), .90))
    elif style == 4:  # Monstercat-like mirrored slim spectrum
        data = bands(values, 64, 2); xs = np.linspace(105, 855, len(data)); center = len(data) / 2
        envelope = .35 + .65 * np.sin(np.linspace(.08, math.pi - .08, len(data)))
        for i, (x, value) in enumerate(zip(xs, data * envelope)):
            top = base - 5 - value * 76
            cv2.line(frame, (int(x), base), (int(x), int(top)), color_at(tokyo, i / len(data)), 2, cv2.LINE_AA)
    elif style == 5:  # CAVA smooth bars
        data = bands(values, 44, 3); xs = np.linspace(80, 880, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            top = int(base - 8 - value * 72); color = color_at(cyan, i / len(data))
            cv2.rectangle(frame, (int(x - 5), top), (int(x + 5), base), color, -1, cv2.LINE_AA)
    elif style == 6:  # rounded neon pills
        data = bands(values, 30, 2); xs = np.linspace(110, 850, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            top = int(base - 7 - value * 78); color = color_at(tokyo, i / len(data))
            cv2.line(frame, (int(x), base - 3), (int(x), top + 3), color, 8, cv2.LINE_AA)
            cv2.circle(frame, (int(x), top + 3), 4, color, -1, cv2.LINE_AA)
    elif style == 7:  # luminous columns, deliberate halo
        data = bands(values, 28, 1); xs = np.linspace(120, 840, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            for row in range(1 + int(value * 8)):
                dots.append((x, base - row * 9, 3.0, color_at(tokyo, i / len(data)), .86))
    elif style == 8:  # deterministic particles following the spectrum
        data = bands(values, 36, 2); xs = np.linspace(90, 870, len(data)); rng = np.random.default_rng(808)
        for i, (x, value) in enumerate(zip(xs, data)):
            count = 1 + int(value * 5)
            for row in range(count):
                jitter = rng.normal(0, 4.0); y = base - (row + .4) * (8 + value * 4) + rng.normal(0, 2)
                dots.append((x + jitter, y, 1.8 + value, color_at(tokyo, i / len(data)), .62 + .3 * value))
    elif style == 9:  # one atmospheric dot path, no connecting line
        data = bands(values, 72, 4); xs = np.linspace(80, 880, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            y = base - 10 - value * 55
            dots.append((x, y, 2.3 + value * 1.2, color_at(pink, i / len(data)), .82))
    elif style == 10:  # Tokyo reference dot gradient
        data = bands(values, 38, 2); xs = np.linspace(90, 870, len(data))
        for i, (x, value) in enumerate(zip(xs, data)):
            rows = 1 + int(value * 8)
            for row in range(rows):
                dots.append((x, base - row * 8, 2.8, color_at(tokyo, .10 + .8 * i / len(data)), .92))
    elif style == 11:  # low soft light blocks
        data = bands(values, 24, 4); xs = np.linspace(115, 845, len(data)); layer = np.zeros_like(frame)
        for i, (x, value) in enumerate(zip(xs, data)):
            top = int(base - 10 - value * 55); color = color_at(pink, i / len(data))
            cv2.line(layer, (int(x), base - 4), (int(x), top), color, 11, cv2.LINE_AA)
        cv2.addWeighted(frame, 1, cv2.GaussianBlur(layer, (0, 0), 6), .46, 0, frame); cv2.addWeighted(frame, 1, layer, .62, 0, frame)
    else:  # designer hybrid: mound body + select short bars
        data = bands(values, 42, 4); xs = np.linspace(75, 885, len(data)); envelope = .55 + .45 * np.sin(np.linspace(.05, math.pi - .05, len(data)))
        for i, (x, value) in enumerate(zip(xs, data * envelope)):
            rows = 1 + int(value * 5)
            for row in range(rows): dots.append((x + (row % 2) * 2, base - row * 9, 2.7, color_at(tokyo, i / len(data)), .78 + .18 * value))
            if i % 7 == 3 and value > .45: cv2.line(frame, (int(x), base), (int(x), int(base - value * 60)), color_at(tokyo, i / len(data)), 2, cv2.LINE_AA)
    if dots:
        glow_dots(frame, dots, blur=4 if style in {3, 7, 8, 10, 12} else 2, strength=.24 if style != 7 else .38)
    return frame


def encode_style(ffmpeg: str, audio: Path, output: Path, features: dict, style: int, seconds: float, fps=24):
    command = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "960x160", "-r", str(fps), "-i", "pipe:0", "-i", str(audio), "-t", str(seconds), "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    spectrum = features["spectrum"]; onset_values = features.get("onset", np.zeros(len(spectrum)))
    total = int(seconds * fps); previous = np.zeros(spectrum.shape[1], np.float32)
    for index in range(total):
        source = spectrum[min(index, len(spectrum) - 1)]; previous = np.maximum(source, previous * .82)
        frame = render_style(style, previous, float(onset_values[min(index, len(onset_values) - 1)]), index / fps)
        process.stdin.write(frame.tobytes())
    process.stdin.close()
    if process.wait(): raise RuntimeError(f"ffmpeg failed for style {style}")


def compose(ffmpeg, wave, background, output, seconds, opacity):
    graph = "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=rgb24[bg];color=c=black:s=1920x1080:r=24[c];[1:v]scale=960:160[w];[c][w]overlay=x=480:y=800:shortest=1[wf];[bg][wf]blend=all_mode=screen:all_opacity=%.2f[out]" % opacity
    command = [ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background), "-i", str(wave), "-filter_complex", graph, "-map", "[out]", "-map", "1:a?", "-t", str(seconds), "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)]
    subprocess.run(command, check=True)


def get_frame(path: Path, seconds: float):
    cap = cv2.VideoCapture(str(path)); cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000); ok, value = cap.read(); cap.release()
    if not ok: raise RuntimeError(path)
    return Image.fromarray(cv2.cvtColor(value, cv2.COLOR_BGR2RGB))


def sheet(paths, target, timestamp, title):
    canvas = Image.new("RGB", (1280, 720), "#090c12"); draw = ImageDraw.Draw(canvas)
    for index, ((slug, name), path) in enumerate(zip(STYLES, paths)):
        x = (index % 4) * 320; y = (index // 4) * 240
        image = get_frame(path, timestamp).resize((320, 180), Image.Resampling.LANCZOS); canvas.paste(image, (x, y))
        draw.rectangle((x, y + 180, x + 320, y + 240), fill="#10151f")
        draw.text((x + 10, y + 190), f"{index + 1:02d} · {name}", font=font(17), fill="#f4f7ff")
        draw.text((x + 10, y + 216), title, font=font(13), fill="#9eabc0")
    canvas.save(target)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--seconds", type=float, default=24); parser.add_argument("--output", type=Path, default=ROOT / "validation_results/visualizer_library_survey"); args = parser.parse_args()
    output = args.output; output.mkdir(parents=True, exist_ok=True); ffmpeg = resolve_ffmpeg(None)
    audio = ROOT / "validation_results/v0839_chill_girl_vibes/validation_fixture_30s.wav"
    if not audio.exists(): audio = ROOT / "sample_assets/audio/sample_10s.wav"
    features, _ = analyze_file(audio, AnalysisSettings(fps=24, bands=64), logger=lambda *_: None)
    wave_paths = []; mid_paths = []; dark_paths = []; start = time.perf_counter()
    for style, (slug, name) in enumerate(STYLES, 1):
        wave = output / f"{slug}.mp4"; encode_style(ffmpeg, audio, wave, features, style, args.seconds); wave_paths.append(wave)
        mid = output / f"STYLE_{style:02d}_mid.mp4"; dark = output / f"STYLE_{style:02d}_dark.mp4"
        compose(ffmpeg, wave, ROOT / "sample_assets/background/v0833_cafe_window_fixture.png", mid, args.seconds, .86)
        compose(ffmpeg, wave, ROOT / "sample_assets/background/v0830_tokyo_night_fixture.png", dark, args.seconds, .78)
        mid_paths.append(mid); dark_paths.append(dark); print(f"{style:02d}/12 {name}", flush=True)
    timestamp = min(17.0, args.seconds * .72)
    sheet(wave_paths, output / "visualizer_12style_contact_sheet.png", timestamp, "Wave only")
    sheet(mid_paths, output / "visualizer_12style_mid_contact_sheet.png", timestamp, "Mid-tone composition")
    sheet(dark_paths, output / "visualizer_12style_dark_contact_sheet.png", timestamp, "Dark composition")
    metadata = [{"number": i, "slug": slug, "name": name, "reference_match": i in {1, 3, 10}} for i, (slug, name) in enumerate(STYLES, 1)]
    (output / "prototype_styles.json").write_text(json.dumps({"seconds": args.seconds, "elapsed": time.perf_counter() - start, "styles": metadata}, indent=2), encoding="utf-8")


if __name__ == "__main__": main()
