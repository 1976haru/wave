from __future__ import annotations

import argparse
import json
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
from tools.visualizer_prototypes.soft_round_led_engine import dot_geometry, load_profiles, render_frame, robust_normalize

OUTPUT = ROOT / "validation_results/multi_channel_visualizer_bakeoff"


def font(size: int, bold=False):
    for name in (("segoeuib.ttf", "malgunbd.ttf") if bold else ("segoeui.ttf", "malgun.ttf")):
        path = Path("C:/Windows/Fonts") / name
        if path.exists(): return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def prepare_audio(ffmpeg: str, source: Path, target: Path, seconds: float) -> None:
    subprocess.run([ffmpeg, "-y", "-v", "error", "-stream_loop", "-1", "-i", str(source), "-t", str(seconds),
                    "-ac", "2", "-ar", "48000", str(target)], check=True)


def prepare_background(source: Path, target: Path, treatment: str) -> None:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None: raise RuntimeError(source)
    if treatment == "tokyo_original":
        cv2.imwrite(str(target), image); return
    luminance = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    luminance = np.power(luminance, .88)[..., None]
    if treatment == "warm_lounge":
        shadow, highlight = np.array([42, 50, 62], np.float32), np.array([210, 232, 248], np.float32)
        saturation_mix = .12
    else:  # paris_autumn
        shadow, highlight = np.array([45, 28, 58], np.float32), np.array([176, 210, 238], np.float32)
        saturation_mix = .18
    graded = shadow * (1 - luminance) + highlight * luminance
    original_gray = cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    result = np.clip(graded * (1 - saturation_mix) + original_gray * saturation_mix, 0, 255).astype(np.uint8)
    cv2.imwrite(str(target), result)


def encode(ffmpeg: str, audio: Path, output: Path, spectrum: np.ndarray, profile: dict, seconds: float, fps=24) -> dict:
    command = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "960x160", "-r", str(fps),
               "-i", "pipe:0", "-i", str(audio), "-t", str(seconds), "-shortest", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE); state = np.zeros(spectrum.shape[1], np.float32)
    counts = []; started = time.perf_counter()
    for frame_index in range(int(seconds * fps)):
        target = spectrum[min(frame_index, len(spectrum)-1)]
        coefficient = float(profile["attack"]) if np.mean(target) > np.mean(state) else 1 - float(profile["release"])
        state += (target - state) * coefficient
        geometry = dot_geometry(profile, state); counts.append(len(geometry))
        process.stdin.write(render_frame(profile, state).tobytes())
    process.stdin.close()
    if process.wait(): raise RuntimeError(profile["key"])
    elapsed = time.perf_counter() - started
    return {"render_fps": int(seconds*fps)/elapsed, "median_dots": float(np.median(counts)), "p90_dots": float(np.percentile(counts, 90))}


def compose(ffmpeg: str, wave: Path, background: Path, target: Path, profile: dict, seconds: float) -> None:
    place = profile["placement"]
    # Both blend inputs must use the same planar RGB format. Mixing rgb24 and
    # yuv420p here silently creates a strong magenta cast in FFmpeg.
    graph = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=gbrp[bg];"
             "color=c=black:s=1920x1080:r=24,format=gbrp[c];[1:v]scale=960:160,format=gbrp[w];"
             f"[c][w]overlay=x={place['x']}:y={place['y']}:shortest=1,format=gbrp[wf];"
             f"[bg][wf]blend=all_mode=screen:all_opacity={place['opacity']},format=yuv420p[out]")
    subprocess.run([ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background), "-i", str(wave),
                    "-filter_complex", graph, "-map", "[out]", "-map", "1:a?", "-t", str(seconds), "-r", "24",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(target)], check=True)


def get_frame(path: Path, timestamp: float) -> Image.Image:
    capture = cv2.VideoCapture(str(path)); capture.set(cv2.CAP_PROP_POS_MSEC, timestamp*1000); ok, image = capture.read(); capture.release()
    if not ok: raise RuntimeError(path)
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def three_sheet(profiles: list[dict], paths: list[Path], target: Path, timestamp: float, label: str) -> None:
    canvas = Image.new("RGB", (1440, 390), "#080b12"); draw = ImageDraw.Draw(canvas)
    for index, (profile, path) in enumerate(zip(profiles, paths)):
        x = index*480; canvas.paste(get_frame(path, timestamp).resize((480, 270), Image.Resampling.LANCZOS), (x, 0))
        draw.rectangle((x, 270, x+480, 390), fill="#10151f")
        draw.text((x+14, 284), f"{profile['key']}  {profile['name']}", font=font(22, True), fill="#f5f7ff")
        draw.text((x+14, 318), f"{profile['channel']} / {label}", font=font(15), fill="#a7b3c8")
        draw.text((x+14, 345), f"{profile['bands']} bands · {profile['active_width']}px · {profile['dot_diameter']}px dots", font=font(14), fill="#dec7e8")
    canvas.save(target)


def nine_sheet(profiles: list[dict], paths: list[Path], target: Path, timestamp: float, label: str) -> None:
    canvas = Image.new("RGB", (1440, 1110), "#080b12"); draw = ImageDraw.Draw(canvas)
    for index, (profile, path) in enumerate(zip(profiles, paths)):
        x, y = (index%3)*480, (index//3)*370
        canvas.paste(get_frame(path, timestamp).resize((480, 270), Image.Resampling.LANCZOS), (x, y))
        draw.rectangle((x, y+270, x+480, y+370), fill="#10151f")
        draw.text((x+14, y+282), f"{profile['key']}  {profile['name']}", font=font(21, True), fill="#f5f7ff")
        draw.text((x+14, y+315), f"{profile['channel']} / {label}", font=font(14), fill="#a7b3c8")
    canvas.save(target)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--seconds", type=float, default=22); parser.add_argument("--output", type=Path, default=OUTPUT); parser.add_argument("--compose-only", action="store_true"); args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True); ffmpeg = resolve_ffmpeg(None); profiles = load_profiles()
    channel_audio = {}; analysis = {}
    if not args.compose_only:
        for profile in profiles:
            channel = profile["channel"]
            if channel in channel_audio: continue
            fixture = args.output / f"_{profile['key'][0]}_audio_fixture.wav"
            prepare_audio(ffmpeg, ROOT/profile["audio"], fixture, args.seconds); channel_audio[channel] = fixture
            features, _ = analyze_file(fixture, AnalysisSettings(fps=24, bands=64), logger=lambda *_: None)
            analysis[channel] = robust_normalize(features["spectrum"])
    backgrounds = {}
    for profile in profiles:
        channel = profile["channel"]
        if channel not in backgrounds:
            target = args.output / f"_{profile['key'][0]}_composition_background.png"
            prepare_background(ROOT/profile["background"], target, profile["background_treatment"])
            backgrounds[channel] = target
    if args.compose_only:
        waves = [args.output/f"{profile['key']}_wave.mp4" for profile in profiles]
        compositions = [args.output/f"{profile['key']}_composition.mp4" for profile in profiles]
        for profile, wave, comp in zip(profiles, waves, compositions):
            compose(ffmpeg, wave, backgrounds[profile["channel"]], comp, profile, args.seconds)
        timestamp = min(15.5, args.seconds*.72)
        for prefix, filename in (("T", "tokyo_3style.png"), ("S", "senior_3style.png"), ("C", "chanson_3style.png")):
            indexes = [i for i, profile in enumerate(profiles) if profile["key"].startswith(prefix)]
            three_sheet([profiles[i] for i in indexes], [compositions[i] for i in indexes], args.output/filename, timestamp, "Composition")
        nine_sheet(profiles, waves, args.output/"multi_channel_9style_wave.png", timestamp, "Wave only")
        nine_sheet(profiles, compositions, args.output/"multi_channel_9style_composition.png", timestamp, "Composition")
        return
    waves, compositions, records = [], [], []
    for profile in profiles:
        key = profile["key"]; wave = args.output/f"{key}_wave.mp4"; comp = args.output/f"{key}_composition.mp4"
        metrics = encode(ffmpeg, channel_audio[profile["channel"]], wave, analysis[profile["channel"]], profile, args.seconds)
        compose(ffmpeg, wave, backgrounds[profile["channel"]], comp, profile, args.seconds)
        waves.append(wave); compositions.append(comp); records.append({**profile, **metrics}); print(key, profile["name"], flush=True)
    timestamp = min(15.5, args.seconds*.72)
    for prefix, filename in (("T", "tokyo_3style.png"), ("S", "senior_3style.png"), ("C", "chanson_3style.png")):
        indexes = [i for i, profile in enumerate(profiles) if profile["key"].startswith(prefix)]
        three_sheet([profiles[i] for i in indexes], [compositions[i] for i in indexes], args.output/filename, timestamp, "Composition")
    nine_sheet(profiles, waves, args.output/"multi_channel_9style_wave.png", timestamp, "Wave only")
    nine_sheet(profiles, compositions, args.output/"multi_channel_9style_composition.png", timestamp, "Composition")
    payload = {"version": "0.8.3.9", "engine": "Soft Round LED", "seconds": args.seconds, "fps": 24,
               "audio_policy": "distinct local fixture per channel", "profiles": records,
               "production_renderer_modified": False, "decision": "USER SELECTS ONE STYLE PER CHANNEL"}
    (args.output/"multi_channel_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["MULTI-CHANNEL VISUALIZER BAKE-OFF", "", "Shared renderer core: Soft Round LED", ""]
    for item in records:
        lines += [f"{item['key']} - {item['name']} ({item['channel']})", f"  bands/width/dot: {item['bands']} / {item['active_width']}px / {item['dot_diameter']}px",
                  f"  gaps: {item['horizontal_gap']}px horizontal / {item['vertical_gap']}px vertical",
                  f"  attack/release/smoothing: {item['attack']} / {item['release']} / {item['smoothing']}",
                  f"  glow inner/outer: {item['inner_glow']} / {item['outer_glow']}", f"  amplitude: {item['amplitude_gain']}",
                  f"  palette: {', '.join(stop[1] for stop in item['gradient_stops'])}", f"  dots median/p90: {item['median_dots']:.0f}/{item['p90_dots']:.0f}", ""]
    lines += ["Production renderer modified: NO", "VERSION: 0.8.3.9", "EXE: NOT BUILT", "Next: USER SELECTS Tokyo 1 / Senior 1 / Chanson 1"]
    (args.output/"multi_channel_report.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__": main()
