from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audio.analyzer import AnalysisSettings, analyze_file
from core.ffmpeg import resolve_ffmpeg
from tools.visualizer_prototypes.multi_channel_bakeoff import font, prepare_background
from tools.visualizer_prototypes.soft_round_led_engine import (
    auto_adapt, dot_geometry, load_modifiers, load_universal_themes,
    measure_audio_presence, render_frame, resolve_universal_profile, robust_normalize,
)

OUTPUT = ROOT / "validation_results/universal_presence_calibration"
AUDIO_KINDS = {
    "A_QUIET": ("sample_assets/sample_music_set/02_sample.wav", "volume=0.055,lowpass=f=4200"),
    "B_SLOW": ("sample_assets/sample_music_set/02_sample.wav", "volume=0.45"),
    "C_CHILL": ("validation_results/v0839_chill_girl_vibes/validation_fixture_30s.wav", "volume=0.82"),
    "D_POP": ("sample_assets/sample_music_set/01_sample.wav", "volume=1.18"),
    "E_COMPRESSED": ("sample_assets/sample_music_set/03_sample.wav", "acompressor=threshold=0.08:ratio=8:attack=8:release=70:makeup=3,alimiter=limit=0.92"),
}
BACKGROUNDS = {
    "DARK": ("sample_assets/background/v0830_tokyo_night_fixture.png", "tokyo_original"),
    "MID": ("sample_assets/background/v0833_cafe_window_fixture.png", "paris_autumn"),
    "BRIGHT": ("sample_assets/background/v0833_daytime_romantic_fixture.png", "warm_lounge"),
}


def prepare_audio(ffmpeg: str, source: Path, target: Path, audio_filter: str, seconds: float) -> None:
    subprocess.run([ffmpeg, "-y", "-v", "error", "-stream_loop", "-1", "-i", str(source), "-t", str(seconds),
                    "-af", audio_filter, "-ar", "48000", "-ac", "2", str(target)], check=True)


def image_brightness(path: Path) -> float:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(path)
    return float(np.mean(image) / 255)


def encode_wave(ffmpeg: str, audio: Path, target: Path, spectrum: np.ndarray, profile: dict,
                seconds: float, fps: int = 24) -> dict:
    command = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "960x160",
               "-r", str(fps), "-i", "pipe:0", "-i", str(audio), "-t", str(seconds), "-shortest",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", str(target)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    state = np.zeros(spectrum.shape[1], np.float32)
    counts, rises = [], []
    started = time.perf_counter()
    for frame_index in range(round(seconds * fps)):
        source = spectrum[min(frame_index, len(spectrum) - 1)]
        coefficient = profile["attack"] if np.mean(source) > np.mean(state) else 1 - profile["release"]
        state += (source - state) * coefficient
        geometry = dot_geometry(profile, state)
        counts.append(len(geometry))
        rises.append(max((profile["floor_y"] - item[1] for item in geometry), default=0))
        process.stdin.write(render_frame(profile, state).tobytes())
    process.stdin.close()
    if process.wait():
        raise RuntimeError(target)
    elapsed = time.perf_counter() - started
    return {"render_fps": round(seconds * fps / elapsed, 2), "median_dots": round(float(np.median(counts)), 1),
            "p90_dots": round(float(np.percentile(counts, 90)), 1),
            "rise_p50": round(float(np.percentile(rises, 50)), 1),
            "rise_p90": round(float(np.percentile(rises, 90)), 1), "rise_max": round(max(rises), 1)}


def compose(ffmpeg: str, wave: Path, background: Path, target: Path, seconds: float, adapt: dict) -> None:
    mode = adapt["blend_mode"]
    if mode == "BRIGHT":
        alpha = min(1.0, .88 + adapt["normal_mix"] * .18)
        graph = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080[bg];"
                 f"[1:v]scale=960:160,colorkey=black:0.055:0.10,colorchannelmixer=aa={alpha:.3f}[w];"
                 "[bg][w]overlay=x=230:y=825:shortest=1,format=yuv420p[out]")
    else:
        opacity = .91 if mode == "MID" else .88
        graph = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=gbrp[bg];"
                 "color=c=black:s=1920x1080:r=24,format=gbrp[c];[1:v]scale=960:160,format=gbrp[w];"
                 "[c][w]overlay=x=230:y=825:shortest=1,format=gbrp[wf];"
                 f"[bg][wf]blend=all_mode=screen:all_opacity={opacity:.3f},format=yuv420p[out]")
    subprocess.run([ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background), "-i", str(wave),
                    "-filter_complex", graph, "-map", "[out]", "-map", "1:a?", "-t", str(seconds), "-r", "24",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(target)], check=True)


def frame(path: Path, timestamp: float, size: tuple[int, int]) -> Image.Image:
    cap = cv2.VideoCapture(str(path)); cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
    ok, value = cap.read(); cap.release()
    if not ok:
        raise RuntimeError(path)
    return Image.fromarray(cv2.cvtColor(value, cv2.COLOR_BGR2RGB)).resize(size, Image.Resampling.LANCZOS)


def theme_sheet(themes: list[dict], paths: list[Path], target: Path, timestamp: float, label: str) -> None:
    canvas = Image.new("RGB", (2240, 260), "#090c13"); draw = ImageDraw.Draw(canvas)
    for index, (theme, path) in enumerate(zip(themes, paths)):
        x = index * 320; canvas.paste(frame(path, timestamp, (320, 180)), (x, 0))
        draw.rectangle((x, 180, x + 320, 260), fill="#111722")
        draw.text((x + 9, 190), theme["display_name"], font=font(17, True), fill="#f6f7fb")
        draw.text((x + 9, 220), label, font=font(12), fill="#aebbd0")
    canvas.save(target)


def matrix_sheet(themes: list[dict], paths: dict[tuple[str, str], Path], target: Path, timestamp: float) -> None:
    canvas = Image.new("RGB", (2240, 1250), "#090c13"); draw = ImageDraw.Draw(canvas)
    for row, audio_id in enumerate(AUDIO_KINDS):
        for col, theme in enumerate(themes):
            x, y = col * 320, row * 250
            canvas.paste(frame(paths[(audio_id, theme["id"])], timestamp, (320, 180)), (x, y))
            draw.rectangle((x, y + 180, x + 320, y + 250), fill="#111722")
            draw.text((x + 8, y + 190), f"{audio_id} / {theme['display_name']}", font=font(14, True), fill="#f6f7fb")
            draw.text((x + 8, y + 218), "STANDARD / AUTO / MID", font=font(11), fill="#aebbd0")
    canvas.save(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg(None); themes = list(load_universal_themes().values()); modifiers = load_modifiers()

    backgrounds = {}
    for mode, (source, treatment) in BACKGROUNDS.items():
        target = args.output / f"_{mode.lower()}_background.png"
        prepare_background(ROOT / source, target, treatment); backgrounds[mode] = target

    audio_data = {}
    for audio_id, (source, audio_filter) in AUDIO_KINDS.items():
        target = args.output / f"_{audio_id.lower()}.wav"
        prepare_audio(ffmpeg, ROOT / source, target, audio_filter, args.seconds)
        features, _ = analyze_file(target, AnalysisSettings(fps=24, bands=64), logger=lambda *_: None)
        stats = measure_audio_presence(target, ffmpeg)
        audio_data[audio_id] = {"path": target, "spectrum": robust_normalize(features["spectrum"]), "stats": stats}

    records, matrix_paths = [], {}
    mid_brightness = image_brightness(backgrounds["MID"])
    for audio_id, data in audio_data.items():
        adapt = auto_adapt(data["spectrum"], mid_brightness, data["stats"])
        for theme in themes:
            profile = resolve_universal_profile(theme, "STANDARD", "STANDARD", "LEFT", adapt=adapt, modifiers=modifiers)
            wave = args.output / f"{audio_id.lower()}_{theme['id'].lower()}_wave.mp4"
            comp = args.output / f"{audio_id.lower()}_{theme['id'].lower()}_mid.mp4"
            metrics = encode_wave(ffmpeg, data["path"], wave, data["spectrum"], profile, args.seconds)
            compose(ffmpeg, wave, backgrounds["MID"], comp, args.seconds, adapt)
            matrix_paths[(audio_id, theme["id"])] = comp
            records.append({"audio": audio_id, "theme": theme["id"], "auto_adapt": adapt, **metrics})
            print(audio_id, theme["id"], metrics["render_fps"], flush=True)

    representative = audio_data["C_CHILL"]
    mode_paths = {mode: [] for mode in BACKGROUNDS}; wave_paths = []
    for theme in themes:
        wave = args.output / f"presence_{theme['id'].lower()}_wave.mp4"
        mid_adapt = auto_adapt(representative["spectrum"], mid_brightness, representative["stats"])
        profile = resolve_universal_profile(theme, "STANDARD", "STANDARD", "LEFT", adapt=mid_adapt, modifiers=modifiers)
        encode_wave(ffmpeg, representative["path"], wave, representative["spectrum"], profile, args.seconds)
        wave_paths.append(wave)
        for mode, background in backgrounds.items():
            adapt = auto_adapt(representative["spectrum"], image_brightness(background), representative["stats"])
            mode_profile = resolve_universal_profile(theme, "STANDARD", "STANDARD", "LEFT", adapt=adapt, modifiers=modifiers)
            mode_wave = args.output / f"_{mode.lower()}_{theme['id'].lower()}_wave.mp4"
            encode_wave(ffmpeg, representative["path"], mode_wave, representative["spectrum"], mode_profile, args.seconds)
            target = args.output / f"presence_{theme['id'].lower()}_{mode.lower()}.mp4"
            compose(ffmpeg, mode_wave, background, target, args.seconds, adapt); mode_paths[mode].append(target)

    timestamp = min(args.seconds * .68, 5.5)
    theme_sheet(themes, wave_paths, args.output / "universal_presence_wave.png", timestamp, "Wave only / Standard")
    for mode in BACKGROUNDS:
        theme_sheet(themes, mode_paths[mode], args.output / f"universal_presence_{mode.lower()}.png", timestamp,
                    f"{mode.title()} adaptive composition")
    matrix_sheet(themes, matrix_paths, args.output / "cross_genre_presence_matrix.png", timestamp)

    gains = {audio_id: auto_adapt(data["spectrum"], mid_brightness, data["stats"])["amplitude_multiplier"]
             for audio_id, data in audio_data.items()}
    payload = {"version": "0.8.3.9", "themes": [item["id"] for item in themes], "audio_validation": {
        key: {"stats": value["stats"], "gain": gains[key]} for key, value in audio_data.items()},
        "auto_gain_range": [min(gains.values()), max(gains.values())], "background_modes": list(BACKGROUNDS),
        "records": records, "average_render_fps": float(np.mean([item["render_fps"] for item in records])),
        "minimum_render_fps": min(item["render_fps"] for item in records),
        "production_renderer_modified": False, "version_changed": False}
    (args.output / "universal_presence_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["UNIVERSAL PRESENCE CALIBRATION", "", "Themes: 7", "Audio validation: 5",
             "Background modes: Bright / Mid / Dark", f"Auto gain range: {min(gains.values()):.3f} - {max(gains.values()):.3f}", ""]
    for audio_id, data in audio_data.items():
        stats = data["stats"]
        lines.append(f"{audio_id}: gain={gains[audio_id]:.3f}, energy={stats['integrated_dbfs']:.2f} dBFS, "
                     f"p20={stats['p20_dbfs']:.2f}, median={stats['median_dbfs']:.2f}, p95={stats['p95_dbfs']:.2f}, "
                     f"crest={stats['crest_factor']:.2f}, dynamic={stats['dynamic_range_db']:.2f} dB, "
                     f"silence={stats['silence_ratio']:.3f}, transients={stats['transient_density']:.3f}")
    lines += ["", f"Average render fps: {payload['average_render_fps']:.2f}",
              f"Minimum render fps: {payload['minimum_render_fps']:.2f}", "Production renderer modified: NO",
              "VERSION: 0.8.3.9", "EXE: NOT BUILT", "Push: NO"]
    (args.output / "universal_presence_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
