from __future__ import annotations

import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/visualizer_survey"
SHOTS = OUT / "screenshots"

SEEDS = """
hvianna/audioMotion-analyzer
foobar404/wave.js
marcopixel/monstercat-visualizer
DevonCrawford/LED-Music-Visualizer
wayou/HTML5_Audio_Visualizer
alex2wong/vudio
margox/vudio.js
wizgrav/clubber
azeem/webvs
NickvisionApps/Cavalier
TheWisker/Cavasik
scottlawsonbc/audio-reactive-led-strip
michaelbromley/soundcloud-visualizer
dominikhofacker/audiovisualization
Yug34/audio-visualizer
mfcc64/youtube-musical-spectrum
jarcode-foss/glava
tlecomte/friture
BaseMax/AudioVisualizerJS
TheNexusAvenger/Monstercat-Audio-Spectrum-Visualizer
Bauxitedev/spectral-visualizer
deftio/WebAudioSpectrum
zogi/spectrum-analyzer-js
clarkezone/audiovisualizer
ranshufang55/sonascope
katspaugh/wavesurfer.js
staskobzar/vue-audio-visual
kelvinau/circular-audio-wave
phip1611/audio-visualizer
ricknout/android-visualizer
evan-moon/simple-waveform-visualizer
chrisweb/waveform-visualizer
mathiasvr/audio-oscilloscope
ndragun92/vue-music-flow
jberg/butterchurn
projectM-visualizer/projectm
zz-plant/stims
jasonulbright/wavescope
EYHN/Azusa
vovoid/vsxu
rocksdanister/audio-visualizer-wallpaper
tgcnzn/Interactive-Particles-Music-Visualizer
SeanFree/musical-particles-v3
SeanFree/musical-particles-v4
fadelakin/Audio_Reactive_Particles
andrinr/frequency-gpu-particles
Blacktea0/play-music-particle-visualizer
nickstanish/visual-audio-js
davidharrigan/Audio-Visualizer-Particles
kevinraymond/fosfora
wayou/3D_Audio_Spectrum_VIsualizer
macobo/WebGL-Audio-Visualization
rolyatmax/audiofabric
DodekaHydra/arcane.gl
wayne-wu/webgl-music-visualizer
jseidelin/webgl-music-visualizer
dcyoung/r3f-audio-visualizer
santosharron/audio-visualizer-three-js
l1ve4code/3d-music-visualizer
kekkorider/threejs-circular-audio-visualizer
""".strip().splitlines()

EXTRA_HINTS = [
    "karlstav/cava", "projectM-visualizer/projectm", "Akira-Taniguchi/AudioVisualizer",
    "cwilso/Audio-Visualizer", "mdn/webaudio-examples", "frequensea/visualizer",
    "caseif/vis.js", "flyingrub/scdlbot", "zachwinter/kaleidosync", "pseudosavant/player-visualizer",
]

FIELDS = [
    "repository", "github_url", "stars", "last_update", "archived", "main_language", "framework", "platform",
    "visualization_type", "bar", "LED", "dots", "particles", "line", "waveform", "radial", "shader", "full_screen",
    "screenshot_demo", "local_demo", "audio_file_input", "microphone_input", "fft_spectrum", "smoothing",
    "color_gradient", "glow", "round_dot_bar", "transparency", "offscreen_rendering", "video_export",
    "license", "license_source", "license_class", "commercial_use_possibility", "source_reuse_possibility",
    "reuse_label", "implementation_difficulty", "reference_similarity", "beauty", "hip_young_appeal",
    "tokyo_chill_suitability", "lower_third_suitability", "background_composition_suitability",
    "implementation_simplicity", "performance", "license_friendliness", "aesthetic_notes", "demo_url",
    "screenshot_file", "readme_checked", "license_file_checked", "availability",
]


def get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MusicWaveStudio-Visualizer-Survey", "Accept": accept})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def text_url(url: str) -> str:
    try:
        return get(url, "text/plain").decode("utf-8", "replace")
    except Exception:
        return ""


def github_repo(repo: str) -> dict | None:
    try:
        return json.loads(get(f"https://api.github.com/repos/{repo}"))
    except Exception:
        return None


def search_repositories() -> list[str]:
    query = urllib.parse.quote('"audio visualizer" in:name,description stars:>5')
    try:
        payload = json.loads(get(f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=100"))
        return [item["full_name"] for item in payload.get("items", [])]
    except Exception:
        return []


def raw_file(repo: str, branch: str, names: list[str]) -> tuple[str, str]:
    for name in names:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{name}"
        value = text_url(url)
        if value:
            return value, url
    return "", ""


def license_info(text: str, spdx: str | None) -> tuple[str, str, str, str]:
    sample = text.lower()
    code = spdx or "NOASSERTION"
    if "gnu affero" in sample or code == "AGPL-3.0":
        return code, "RED", "conditions/high copyleft", "REFERENCE_ONLY"
    # LGPL contains the GPL name in its full license text, so conditional
    # licenses must be detected before the generic GPL branch.
    if "lesser general public" in sample or code.startswith("LGPL") or code.startswith("MPL"):
        return code, "YELLOW", "conditional; notice/linking obligations", "SAFE_TO_STUDY"
    if "gnu general public license" in sample or code.startswith("GPL"):
        return code, "RED", "copyleft; production copy prohibited without review", "REFERENCE_ONLY"
    permissive = ("permission is hereby granted" in sample or "apache license" in sample or "redistribution and use" in sample or code in {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "0BSD"})
    if permissive:
        return code, "GREEN", "likely yes; preserve notices and re-check dependencies", "DIRECT_REUSE_ALLOWED"
    return code, "RED", "unknown/no clear license", "REFERENCE_ONLY"


def flags(readme: str, description: str) -> dict:
    lower = f"{description} {readme[:25000]}".lower()
    has = lambda *words: any(word in lower for word in words)
    types = []
    for label, words in {
        "LED": ("led",), "dots": ("dot", "point sprite"), "particles": ("particle",), "bars": ("bar", "spectrum"),
        "waveform": ("waveform", "oscilloscope"), "radial": ("radial", "circular"), "shader": ("shader", "glsl"),
        "line": ("line", "curve"), "full-screen": ("fullscreen", "wallpaper", "milkdrop"),
    }.items():
        if has(*words):
            types.append(label)
    return {
        "visualization_type": ", ".join(types) or "audio reactive / unspecified",
        "bar": has("bar", "spectrum"), "LED": has("led"), "dots": has("dot", "point sprite"),
        "particles": has("particle"), "line": has("line", "curve"), "waveform": has("waveform", "oscilloscope"),
        "radial": has("radial", "circular"), "shader": has("shader", "glsl", "webgl"), "full_screen": has("fullscreen", "wallpaper", "milkdrop"),
        "screenshot_demo": has("demo", "screenshot", ".gif", ".png", "youtube", "github.io"),
        "local_demo": has("npm install", "yarn", "index.html", "cmake", "build"),
        "audio_file_input": has("audio file", "upload", "mp3", "soundcloud", "local file"),
        "microphone_input": has("microphone", "getusermedia", "audio input", "pulseaudio"),
        "fft_spectrum": has("fft", "frequencybin", "analysernode", "spectrum"),
        "smoothing": has("smooth", "smoothingtimeconstant", "decay", "falloff", "averag"),
        "color_gradient": has("gradient", "color", "colour", "palette"), "glow": has("glow", "blur", "bloom", "neon"),
        "round_dot_bar": has("round", "dot", "led"), "transparency": has("alpha", "transparent", "opacity"),
        "offscreen_rendering": has("offscreen", "headless", "canvas", "framebuffer"), "video_export": has("video", "record", "export", "ffmpeg"),
    }


def framework(language: str, readme: str) -> tuple[str, str]:
    lower = readme.lower()
    candidates = [name for name in ("three.js", "p5.js", "web audio", "canvas", "webgl", "react", "vue", "qt", "gtk", "opengl", "android") if name in lower]
    platform = "Web" if language in {"JavaScript", "TypeScript", "HTML"} else ("Android" if "android" in lower or language in {"Kotlin", "Java"} else "Desktop/native")
    return ", ".join(candidates) or language or "Unknown", platform


def score(repo: str, info: dict, detected: dict, license_class: str) -> dict:
    lower = f"{repo} {info.get('description') or ''}".lower()
    reference = 22 + 18 * detected["dots"] + 12 * detected["LED"] + 10 * detected["bar"] + 10 * detected["glow"] + 8 * detected["transparency"]
    lower_third = 40 + 16 * detected["bar"] + 12 * detected["dots"] - 15 * detected["radial"] - 18 * detected["full_screen"]
    beauty = 42 + 9 * detected["color_gradient"] + 10 * detected["glow"] + 8 * detected["particles"] + min(12, int(np_log_stars(info.get("stargazers_count", 0))))
    hip = beauty + 7 * detected["dots"] + 6 * detected["particles"] + 5 * detected["shader"] - 4 * detected["LED"]
    simplicity = 82 - 25 * detected["shader"] - 18 * detected["particles"] - 12 * detected["full_screen"] + 8 * detected["bar"] + 6 * detected["dots"]
    performance = 78 - 22 * detected["particles"] - 18 * detected["shader"] - 8 * detected["full_screen"] + 8 * detected["bar"]
    license_score = {"GREEN": 95, "YELLOW": 58, "RED": 20}[license_class]
    tokyo = int((reference + beauty + hip + lower_third) / 4)
    composition = int((lower_third + beauty + (80 if detected["transparency"] else 55)) / 3)
    values = {
        "reference_similarity": reference, "beauty": beauty, "hip_young_appeal": hip,
        "tokyo_chill_suitability": tokyo, "lower_third_suitability": lower_third,
        "background_composition_suitability": composition, "implementation_simplicity": simplicity,
        "performance": performance, "license_friendliness": license_score,
    }
    return {key: int(max(0, min(100, value))) for key, value in values.items()}


def np_log_stars(stars: int) -> float:
    import math
    return math.log10(max(1, stars)) * 3


def first_image(readme: str, repo: str, branch: str) -> str:
    matches = re.findall(r"!\[[^\]]*\]\(([^ )]+)|<img[^>]+src=[\"']([^\"']+)", readme, re.I)
    for match in matches:
        url = next((part for part in match if part), "").strip()
        if not url or url.startswith("data:") or "badge" in url.lower() or "shield" in url.lower():
            continue
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://github.com" + url
        elif not url.startswith("http"):
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{url.lstrip('./')}"
        return url.replace("github.com/", "raw.githubusercontent.com/").replace("/blob/", "/") if "/blob/" in url else url
    return ""


def save_screenshot(index: int, repo: str, url: str) -> str:
    if not url:
        return ""
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        suffix = ".png"
    target = SHOTS / f"{index:03d}_{repo.replace('/', '_')}{suffix}"
    try:
        target.write_bytes(get(url, "image/*"))
        return str(target.relative_to(ROOT))
    except Exception:
        return ""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    search = search_repositories()
    queue = list(dict.fromkeys(SEEDS + EXTRA_HINTS + search))
    rows = []
    for repo in queue:
        if len(rows) >= 60:
            break
        info = github_repo(repo)
        if not info or info.get("fork"):
            continue
        canonical = info["full_name"]
        branch = info.get("default_branch") or "master"
        readme, _ = raw_file(canonical, branch, ["README.md", "readme.md", "README.MD", "README", "docs/README.md"])
        license_text, license_url = raw_file(canonical, branch, ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md"])
        detected = flags(readme, info.get("description") or "")
        code, license_class, commercial, reuse = license_info(license_text, (info.get("license") or {}).get("spdx_id"))
        language = info.get("language") or "Unknown"
        fw, platform = framework(language, readme)
        scores = score(canonical, info, detected, license_class)
        demo = info.get("homepage") or ""
        image_url = first_image(readme, canonical, branch)
        screenshot = save_screenshot(len(rows) + 1, canonical, image_url)
        difficulty = "LOW" if scores["implementation_simplicity"] >= 72 else ("MEDIUM" if scores["implementation_simplicity"] >= 48 else "HIGH")
        notes = []
        if detected["dots"] or detected["LED"]:
            notes.append("Discrete light vocabulary relevant to the reference")
        if detected["bar"]:
            notes.append("Frequency aggregation and spacing worth studying")
        if detected["particles"] or detected["shader"]:
            notes.append("Art direction useful; direct long-form port may be expensive")
        row = {
            "repository": canonical, "github_url": info["html_url"], "stars": info.get("stargazers_count", 0),
            "last_update": info.get("pushed_at") or info.get("updated_at"), "archived": info.get("archived", False),
            "main_language": language, "framework": fw, "platform": platform, **detected,
            "license": code, "license_source": license_url, "license_class": license_class,
            "commercial_use_possibility": commercial, "source_reuse_possibility": reuse,
            "reuse_label": reuse, "implementation_difficulty": difficulty, **scores,
            "aesthetic_notes": "; ".join(notes) or "General motion/color reference",
            "demo_url": demo, "screenshot_file": screenshot, "readme_checked": bool(readme),
            "license_file_checked": bool(license_text), "availability": "AVAILABLE",
        }
        rows.append(row)
        print(f"{len(rows):02d}/60 {canonical} {code} {license_class}", flush=True)
        time.sleep(.08)
    if len(rows) < 60:
        raise RuntimeError(f"Only {len(rows)} available repositories could be reviewed")
    json_path = OUT / "visualizer_library_matrix.json"
    csv_path = OUT / "visualizer_library_matrix.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    ranked = sorted(rows, key=lambda row: (row["tokyo_chill_suitability"] + row["reference_similarity"] + row["beauty"]), reverse=True)
    lines = ["# Visualizer Library Matrix", "", f"Reviewed: {len(rows)} repositories", "", "| # | Repository | Stars | Type | License | Class | Reference | Beauty | Tokyo Chill | Notes |", "|---:|---|---:|---|---|---|---:|---:|---:|---|"]
    for index, row in enumerate(ranked, 1):
        lines.append(f"| {index} | [{row['repository']}]({row['github_url']}) | {row['stars']} | {row['visualization_type']} | {row['license']} | {row['license_class']} | {row['reference_similarity']} | {row['beauty']} | {row['tokyo_chill_suitability']} | {row['aesthetic_notes']} |")
    (OUT / "visualizer_library_matrix.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"reviewed": len(rows), "screenshots": sum(bool(row["screenshot_file"]) for row in rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
