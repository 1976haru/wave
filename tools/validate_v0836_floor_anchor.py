from __future__ import annotations

import json
import sys
import time
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.exporter import ExportOptions, render_audio
from render.renderer import CPURenderer, signature_instances
from template_system import load_template


PRESETS = {
    "HIS": "templates/00_v0834_tokyo_chill_his.json",
    "DUAL": "templates/00_v0834_tokyo_chill_dual.json",
    "HER": "templates/00_v0834_tokyo_chill_her.json",
}


def join_fixture(target: Path) -> None:
    sources = sorted((ROOT / "sample_assets" / "sample_music_set").glob("*.wav"))
    with wave.open(str(sources[0]), "rb") as first:
        params = first.getparams()
    with wave.open(str(target), "wb") as output:
        output.setparams(params)
        for source in sources:
            with wave.open(str(source), "rb") as stream:
                if stream.getparams()[:4] != params[:4]:
                    raise RuntimeError(f"Incompatible fixture: {source}")
                output.writeframes(stream.readframes(stream.getnframes()))


def state(template: dict, level: float, onset: float, seconds: float) -> dict:
    count = int(template["bands"])
    values = np.linspace(level * .75, level, count, dtype=np.float32)
    return {
        "values": values,
        "left_values": np.roll(values, 1) * .97,
        "right_values": np.roll(values, -2) * 1.02,
        "bass": level,
        "mid": level * .85,
        "high": level * .60,
        "onset": onset,
        "time": seconds,
    }


def metrics(template: dict) -> dict:
    base = 160 * float(template["anchor_y"])
    heights = {}
    colours = 0
    for label, level, onset in (("quiet", .18, 0), ("medium", .48, .25), ("strong", .86, .80)):
        dots, lines = signature_instances(960, 160, state(template, level, onset, 4), template)
        y = np.asarray([dot[1] for dot in dots], np.float32)
        heights[label] = round(base - float(y.min()), 2)
        if label == "strong":
            colours = len({dot[3] for dot in dots})
            max_y = max(float(y.max()), *(float(np.asarray(line["points"])[:, 1].max()) for line in lines))
            floor_ok = max_y <= base + .05
    renderer = CPURenderer()
    render_state = state(template, .62, .45, 8)
    start = time.perf_counter()
    frames = 120
    for _ in range(frames):
        renderer.render_rgba(960, 160, render_state, template)
    fps = frames / (time.perf_counter() - start)
    return {
        "baseline_y": base,
        **{f"{key}_height": value for key, value in heights.items()},
        "max_height": heights["strong"],
        "strong_quiet_delta": round(heights["strong"] - heights["quiet"], 2),
        "unique_color_count": colours,
        "renderer": renderer.name,
        "average_fps": round(fps, 2),
        "floor_anchor_pass": floor_ok,
        "pass": floor_ok and heights["strong"] >= 85 and heights["strong"] - heights["quiet"] >= 45 and 6 <= colours <= 32,
    }


def video_frame(path: Path, seconds: float) -> Image.Image:
    capture = cv2.VideoCapture(str(path))
    capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError(f"Cannot read {path} at {seconds}s")
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def contact_sheet(videos: dict[str, Path], target: Path) -> None:
    times = (1.0, 11.0, 21.0, 26.0)
    labels = ("quiet", "medium", "strong", "onset peak")
    sheet = Image.new("RGB", (960, 3 * 210), "#10131a")
    draw = ImageDraw.Draw(sheet)
    for row, (name, path) in enumerate(videos.items()):
        for col, (seconds, label) in enumerate(zip(times, labels)):
            frame = video_frame(path, seconds).resize((240, 160))
            sheet.paste(frame, (col * 240, row * 210))
            draw.text((col * 240 + 8, row * 210 + 166), f"{name} · {label} · {seconds:.0f}s", fill="#f1f4fa")
    sheet.save(target)


def main() -> int:
    output = ROOT / "validation_results" / "v0836_floor_anchor"
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / "validation_fixture_30s.wav"
    join_fixture(fixture)
    videos: dict[str, Path] = {}
    report = {"version": "0.8.3.6", "fixture": str(fixture), "presets": {}}
    for name, template_path in PRESETS.items():
        template = load_template(ROOT / template_path)
        video = output / f"{name}_v0836_preview.mp4"
        render = render_audio(
            fixture,
            video,
            template,
            ExportOptions(960, 160, 24, "QUALITY", "CPU", "mp4", crf=18),
            logger=lambda message: print(f"[{name}] {message}"),
        )
        item = metrics(template)
        item.update({"video": str(video), "render_seconds": round(render["seconds"], 2), "render_average_fps": round(render["average_fps"], 2)})
        report["presets"][name] = item
        videos[name] = video
    contact_sheet(videos, output / "contact_sheet.png")
    (output / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["Music Wave Studio v0.8.3.6 floor-anchor validation", ""]
    for name, item in report["presets"].items():
        lines.extend([f"{name}: {'PASS' if item['pass'] else 'FAIL'}"] + [f"{key}: {value}" for key, value in item.items()] + [""])
    (output / "validation_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["pass"] for item in report["presets"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
