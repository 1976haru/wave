from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ffmpeg import resolve_ffmpeg


PRESETS = {
    "HIS": "HIS_v0838_preview.mp4",
    "DUAL": "DUAL_v0838_preview.mp4",
    "HER": "HER_v0838_preview.mp4",
}
BACKGROUNDS = {
    "bright": ROOT / "sample_assets/background/v0833_daytime_romantic_fixture.png",
    "mid": ROOT / "sample_assets/background/v0833_cafe_window_fixture.png",
    "dark": ROOT / "sample_assets/background/v0830_tokyo_night_fixture.png",
}
OPACITY = {"bright": .96, "mid": .86, "dark": .76}
LABELS = {"wave": "Wave only", "bright": "Bright comp", "mid": "Mid-tone comp", "dark": "Dark comp"}


def font(size: int):
    for candidate in (Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\malgun.ttf")):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def run(command: list[str]) -> None:
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError(process.stderr[-2000:])


def compose(ffmpeg: str, wave: Path, background: Path, output: Path, seconds: float, opacity: float) -> None:
    # A black full-frame carrier preserves the compact waveform's exact geometry;
    # Screen then removes black in the same visual manner as the CapCut workflow.
    filter_graph = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=rgb24[bg];"
        "color=c=black:s=1920x1080:r=24[carrier];"
        "[1:v]scale=960:160:flags=lanczos[wave];"
        "[carrier][wave]overlay=x=480:y=800:shortest=1[wavefull];"
        f"[bg][wavefull]blend=all_mode=screen:all_opacity={opacity:.2f}[out]"
    )
    command = [
        ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background), "-i", str(wave),
        "-filter_complex", filter_graph, "-map", "[out]", "-map", "1:a?", "-t", f"{seconds:.3f}",
        "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(output),
    ]
    run(command)


def frame(path: Path, seconds: float) -> np.ndarray:
    capture = cv2.VideoCapture(str(path))
    capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ok, value = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError(f"Cannot read frame: {path}")
    return cv2.cvtColor(value, cv2.COLOR_BGR2RGB)


def panel(value: np.ndarray, label: str) -> Image.Image:
    image = Image.fromarray(value).resize((960, 540), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((20, 18, 250, 68), radius=12, fill=(0, 0, 0, 165))
    draw.text((38, 29), label, font=font(24), fill="white")
    return image


def wave_panel(path: Path, seconds: float) -> Image.Image:
    raw = Image.fromarray(frame(path, seconds)).resize((960, 160), Image.Resampling.LANCZOS)
    result = Image.new("RGB", (960, 540), "black")
    result.paste(raw, (0, 300))
    draw = ImageDraw.Draw(result, "RGBA")
    draw.rounded_rectangle((20, 18, 250, 68), radius=12, fill=(15, 18, 28, 220))
    draw.text((38, 29), LABELS["wave"], font=font(24), fill="white")
    return result


def comparison_board(name: str, wave: Path, compositions: dict[str, Path], target: Path, seconds: float) -> None:
    board = Image.new("RGB", (1920, 1080), "#0b0e14")
    board.paste(wave_panel(wave, seconds), (0, 0))
    board.paste(panel(frame(compositions["bright"], seconds), LABELS["bright"]), (960, 0))
    board.paste(panel(frame(compositions["mid"], seconds), LABELS["mid"]), (0, 540))
    board.paste(panel(frame(compositions["dark"], seconds), LABELS["dark"]), (960, 540))
    draw = ImageDraw.Draw(board, "RGBA")
    draw.rectangle((0, 1024, 1920, 1080), fill=(4, 6, 12, 220))
    draw.text((28, 1034), f"{name} · Tokyo Chill composition A/B · same frame {seconds:.1f}s", font=font(25), fill="#f4f7ff")
    board.save(target)


def heuristic(wave_path: Path, comp_path: Path, seconds: float) -> dict:
    raw = frame(wave_path, seconds)
    mask = cv2.cvtColor(raw, cv2.COLOR_RGB2GRAY) > 24
    occupied = float(mask.mean())
    comp = frame(comp_path, seconds)
    crop = comp[800:960, 480:1440]
    luminance = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    if np.any(mask) and np.any(~mask):
        contrast = abs(float(luminance[mask].mean()) - float(luminance[~mask].mean()))
        prominence = float(np.percentile(luminance[mask], 90) - np.percentile(luminance[~mask], 50))
    else:
        contrast = prominence = 0.0
    visibility = int(np.clip(contrast * 1.25 + prominence * .55, 0, 100))
    harmony = int(np.clip(92 - abs(visibility - 66) * .42 - max(0, occupied - .16) * 120, 0, 100))
    return {
        "visibility_score": visibility,
        "composition_harmony": harmony,
        "occupied_pixel_ratio": round(occupied, 4),
        "clutter_risk": "low" if occupied < .12 else ("medium" if occupied < .20 else "high"),
    }


def write_report(output: Path, results: dict, seconds: float) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "unknown"
    lines = [
        "Tokyo Chill Composition Review", "",
        "version: 0.8.3.8", f"commit: {commit}", "resolution: 1920x1080", "fps: 24",
        f"duration: {seconds:.1f}s", "composition mode: screen-like blend over local copyright-safe fixtures", "",
    ]
    mode_notes = {
        "bright": "밝은 실전 배경: visibility가 낮으면 opacity 소폭 상승 후보",
        "mid": "표준 도시 무드: 일반적인 Tokyo Chill 채널 배치 판단용",
        "dark": "야간 네온 무드: highlight와 hero peak 존재감 판단용",
    }
    for name, data in results.items():
        ranked = sorted(data.items(), key=lambda item: item[1]["composition_harmony"], reverse=True)
        lines += [f"[{name}]", "wave only: sparse geometry와 hero peak 자체 형태 확인"]
        for mode in ("bright", "mid", "dark"):
            item = data[mode]
            lines.append(f"{mode}: {mode_notes[mode]} | visibility={item['visibility_score']}/100 harmony={item['composition_harmony']}/100 clutter={item['clutter_risk']} occupied={item['occupied_pixel_ratio']}")
        lines += [f"recommended best background mode: {ranked[0][0]}", f"recommended weakest mode: {ranked[-1][0]}", "final aesthetic judgment: USER REVIEW REQUIRED", ""]
    (output / "composition_review_report.txt").write_text("\n".join(lines), encoding="utf-8")
    (output / "composition_review_report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def build(seconds: float, source_dir: Path, output: Path) -> dict:
    ffmpeg = resolve_ffmpeg(None)
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required")
    output.mkdir(parents=True, exist_ok=True)
    review_time = min(18.0, max(.25, seconds * .72))
    results: dict[str, dict] = {}
    boards = []
    for name, source_name in PRESETS.items():
        source = source_dir / source_name
        if not source.exists():
            raise FileNotFoundError(f"Missing v0.8.3.8 preview: {source}")
        wave = output / f"{name}_wave_only.mp4"
        shutil.copy2(source, wave)
        compositions = {}
        results[name] = {}
        for mode, background in BACKGROUNDS.items():
            target = output / f"{name}_{mode}_comp.mp4"
            compose(ffmpeg, wave, background, target, seconds, OPACITY[mode])
            compositions[mode] = target
            results[name][mode] = heuristic(wave, target, review_time)
        board = output / f"{name}_comparison_board.png"
        comparison_board(name, wave, compositions, board, review_time)
        boards.append(Image.open(board).resize((960, 540), Image.Resampling.LANCZOS))
    sheet = Image.new("RGB", (960, 1620), "#080b11")
    for index, board in enumerate(boards):
        sheet.paste(board, (0, index * 540))
    sheet.save(output / "composition_contact_sheet.png")
    write_report(output, results, seconds)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Tokyo Chill waveform/composition A/B review assets")
    parser.add_argument("--seconds", type=float, default=24.0)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "validation_results/v0838_premium_neon_dots")
    parser.add_argument("--output", type=Path, default=ROOT / "validation_results/tokyo_chill_composition_review")
    parser.add_argument("--all", action="store_true", help="Build all stable Tokyo Chill signatures (default behavior)")
    args = parser.parse_args()
    results = build(max(1.0, min(args.seconds, 30.0)), args.source_dir, args.output)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
