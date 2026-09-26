from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/visualizer_survey"
MATRIX = OUT / "visualizer_library_matrix.json"
SCORE_KEYS = ("reference_similarity", "beauty", "hip_young_appeal", "tokyo_chill_suitability",
              "lower_third_suitability", "background_composition_suitability",
              "implementation_simplicity", "performance", "license_friendliness")


def get_font(size: int, bold: bool = False):
    for name in (("segoeuib.ttf", "malgunbd.ttf") if bold else ("segoeui.ttf", "malgun.ttf")):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def score(row: dict) -> float:
    weights = (1.25, 1.15, 1, 1.25, 1.2, 1.15, .7, .55, .55)
    return sum(float(row.get(k, 0)) * w for k, w in zip(SCORE_KEYS, weights)) / sum(weights)


def correct_license(rows: list[dict]) -> None:
    for row in rows:
        if str(row.get("license", "")).startswith(("LGPL", "MPL")):
            row.update(license_class="YELLOW", commercial_use_possibility="conditional; notice/linking obligations",
                       source_reuse_possibility="SAFE_TO_STUDY", reuse_label="SAFE_TO_STUDY",
                       license_friendliness=58)


def write_matrix(rows: list[dict]) -> None:
    fields = list(rows[0])
    with (OUT / "visualizer_library_matrix.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields); writer.writeheader(); writer.writerows(rows)
    MATRIX.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Audio Visualizer Library Matrix", "", f"Reviewed: **{len(rows)} repositories**", "",
             "License labels are research triage, not legal advice.", "",
             "| # | Repository | Stars | Style | License | Class | Ref | Tokyo | Reuse |",
             "|---:|---|---:|---|---|---|---:|---:|---|"]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | [{r['repository']}]({r['github_url']}) | {r['stars']} | {r['visualization_type']} | {r['license']} | {r['license_class']} | {r['reference_similarity']} | {r['tokyo_chill_suitability']} | {r['reuse_label']} |")
    (OUT / "visualizer_library_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def shortlists(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    top25 = sorted(rows, key=score, reverse=True)[:25]
    top15 = sorted(top25, key=lambda r: r["reference_similarity"] + r["tokyo_chill_suitability"] + r["background_composition_suitability"], reverse=True)[:15]
    for stem, values in (("shortlist_top25", top25), ("shortlist_tokyo15", top15)):
        (OUT / f"{stem}.json").write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [f"# {stem.replace('_', ' ').title()}", "", "Scores are screening aids; screenshots and motion remain primary evidence.", "",
                 "| # | Repository | Ref | Beauty | Hip | Tokyo | Lower | Comp | Simple | Perf | License |",
                 "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for i, r in enumerate(values, 1):
            values_text = " | ".join(str(r[k]) for k in SCORE_KEYS)
            lines.append(f"| {i} | [{r['repository']}]({r['github_url']}) | {values_text} |")
        (OUT / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return top25, top15


def thumbnail(row: dict, size=(520, 220)) -> Image.Image:
    path = ROOT / str(row.get("screenshot_file", ""))
    try:
        image = Image.open(path); image.seek(0); image = image.convert("RGB"); image.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", size, "#080b12"); canvas.paste(image, ((size[0]-image.width)//2, (size[1]-image.height)//2)); return canvas
    except Exception:
        canvas = Image.new("RGB", size, "#111526"); draw = ImageDraw.Draw(canvas)
        colors = ("#ff4fa3", "#b77cff", "#42d9ff")
        for i in range(31):
            x = 28 + i * 15; h = 14 + ((i * 17 + len(row["repository"])) % 82)
            draw.rounded_rectangle((x, size[1]-28-h, x+6, size[1]-28), 3, fill=colors[i % 3])
        draw.text((22, 18), "No embeddable README image", font=get_font(18), fill="#aeb9d1"); return canvas


def boards(rows: list[dict]) -> None:
    selected = sorted(rows, key=lambda r: (bool(r.get("screenshot_file")), score(r)), reverse=True)[:20]
    for page in range(2):
        canvas = Image.new("RGB", (1200, 1440), "#080b12"); draw = ImageDraw.Draw(canvas)
        draw.text((36, 22), f"Visualizer Library Reference TOP 20 - {page+1}/2", font=get_font(30, True), fill="#f4f7ff")
        for n, r in enumerate(selected[page*10:(page+1)*10]):
            x, y = 35 + (n % 2)*580, 75 + (n // 2)*270; canvas.paste(thumbnail(r), (x, y))
            draw.text((x+8, y+225), f"{page*10+n+1:02d}  {r['repository']}", font=get_font(17, True), fill="#ffffff")
            draw.text((x+8, y+248), f"{r['license']} / {r['license_class']} | {r['visualization_type'][:48]}", font=get_font(13), fill="#a8b4ca")
        canvas.save(OUT / f"library_reference_top20_{page+1:02d}.png")


def report(rows: list[dict], top25: list[dict], top15: list[dict]) -> None:
    count = Counter(r["license_class"] for r in rows)
    lines = ["# FINAL VISUALIZER SURVEY", "", "## Scope", "",
             f"- GitHub projects searched and deeply reviewed: **{len(rows)}**",
             f"- README/source context checked: **{sum(bool(r['readme_checked']) for r in rows)}**",
             f"- Repository LICENSE files directly found: **{sum(bool(r['license_file_checked']) for r in rows)}**",
             f"- License triage: GREEN {count['GREEN']} / YELLOW {count['YELLOW']} / RED {count['RED']}",
             "- Production renderer changed: **NO**", "- Version changed: **NO (0.8.3.9)**", "",
             "> License labels are preliminary engineering triage, not legal advice. Re-check the exact version and dependencies before reuse.", "",
             "## First shortlist - 25", ""]
    lines += [f"{i}. **{r['repository']}** — {r['visualization_type']}; {r['license']} / {r['license_class']}; ref {r['reference_similarity']}, beauty {r['beauty']}, Tokyo {r['tokyo_chill_suitability']}." for i, r in enumerate(top25, 1)]
    lines += ["", "## Tokyo Chill visual shortlist - 15", ""]
    lines += [f"{i}. **{r['repository']}** — Ref {r['reference_similarity']}, Beauty {r['beauty']}, Hip {r['hip_young_appeal']}, Lower-third {r['lower_third_suitability']}, Composition {r['background_composition_suitability']}, License {r['license_class']}." for i, r in enumerate(top15, 1)]
    lines += ["", "## Prototype set - 12 distinct visual languages", "",
        "| # | Prototype | Extracted principle | Strength | Risk |", "|---:|---|---|---|---|",
        "| 01 / R1 | Reference LED Dot Spectrum | 30 bands, discrete round LEDs, restrained pink | Closest literal match; cheap CPU path | Conventional without careful spacing |",
        "| 02 | True LED Spectrum | 48 segmented levels and level colour | Clear energy and LED identity | Analyzer-like |",
        "| 03 / R2 | Soft Round LED | 34 bands, smoothing, breathing room, halo | Premium evolution of R1 | Bright scenes need opacity lift |",
        "| 04 | Monstercat Minimal | 64 slim bars under broad envelope | Music-video motion clarity | Familiar spectrum vocabulary |",
        "| 05 | CAVA Smooth Bars | 44 heavily smoothed blocks | Stable long-form rhythm | Rectangular if unchanged |",
        "| 06 | Rounded Neon Bars | 30 pill bars and round caps | Youthful neon graphic | Can dominate the scene |",
        "| 07 | Dot + Glow Columns | 28 dot columns, additive halo | Atmospheric on dark footage | Glow can soften detail |",
        "| 08 | Particle Spectrum | Deterministic band-following particles | Organic and unusual | Higher CPU/noise risk |",
        "| 09 | Minimal Wave Dots | One smoothed dot path, no contour | Decorative, non-technical | Weak on bright footage |",
        "| 10 / R3 | Tokyo Gradient Dots | 38 LEDs, pink-purple-cyan gradient | Most Tokyo-Chill-ready | Avoid rainbow drift |",
        "| 11 | Soft Equalizer Lights | 24 blurred light pillars | Beautiful background integration | Low frequency readability |",
        "| 12 | Designer Hybrid | Mound envelope, dots, sparse accents | Most authored silhouette | More tuning and QA |", "",
        "## Why the strongest references look good", "",
        "- Perceptual/log frequency aggregation prevents treble bins consuming the full width.",
        "- Soft compression plus attack/release keeps quiet music visible without making every frame loud.",
        "- LED quantization converts raw FFT into a designed object; 28–38 columns is closest to the user reference.",
        "- Dot diameter and x/y gaps preserve scene space and are as important as amplitude.",
        "- Three controlled colour stops outperform unrestricted hue cycling; highlights should be level-driven.",
        "- A small core plus weak halo retains dot identity under Screen blend.",
        "- Deterministic smoothing and peak falloff protect long-form stability and preview/export parity.", "",
        "## Findings requiring user selection", "",
        "- **Most reference-like:** Style 01 / R1, followed by Style 03 / R2.",
        "- **Most beautiful:** Style 03 / R2 and Style 10 / R3.",
        "- **Most hip / Tokyo Chill:** Style 10 / R3.",
        "- **Most lightweight:** Style 01 / R1.",
        "- **Best fit for current Python/OpenCV renderer:** Styles 01, 03, 07 and 10; no Node/Chromium runtime needed.",
        "- **Dark:** Style 10; **mid-tone:** Style 03. Bright footage needs a small opacity/core-alpha increase.",
        "- No winner is promoted. **USER SELECTION REQUIRED.**", "",
        "## Top library inspirations", "",
        "1. audioMotion-analyzer — True LED, gradients, spacing, smoothing (AGPL: reference-only).",
        "2. wave.js — broad Canvas mode vocabulary.", "3. monstercat-visualizer — lower-third music-video balance.",
        "4. Cavalier — smooth configurable curves/bars.", "5. Cavasik — spectrum aesthetics (GPL: reference-only).",
        "6. audio-reactive-led-strip — energy-to-colour response.", "7. clubber — musical band extraction.",
        "8. HTML5_Audio_Visualizer — simple Canvas/Web Audio mapping.", "9. butterchurn — palette timing and reactivity.",
        "10. projectM — mature motion/palette reference; conditional review required.", "",
        "## Production feasibility and risks", "",
        "- LED/dot candidates map directly to ModernGL instancing and NumPy/OpenCV fallback.",
        "- Avoid Chromium/Node runtime dependencies for offline, long-form Windows packaging.",
        "- Particle/shader engines increase package size, determinism risk and CPU cost.",
        "- GPL/AGPL/no-license sources remain design references; do not copy production source.",
        "- Downloaded screenshots are internal comparison material, not distributable assets.", "",
        "## Artifacts", "", "- `visualizer_library_matrix.csv/json/md`", "- `shortlist_top25.md/json`",
        "- `shortlist_tokyo15.md/json`", "- `library_reference_top20_01.png`, `library_reference_top20_02.png`",
        "- 12 wave-only, 12 Mid, and 12 Dark MP4s", "- Three 12-style contact sheets", ""]
    (OUT / "FINAL_VISUALIZER_SURVEY.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = json.loads(MATRIX.read_text(encoding="utf-8")); correct_license(rows); write_matrix(rows)
    top25, top15 = shortlists(rows); boards(rows); report(rows, top25, top15)
    print(dict(Counter(r["license_class"] for r in rows)), len(rows), len(top25), len(top15))


if __name__ == "__main__":
    main()
