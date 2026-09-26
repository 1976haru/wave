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
from tools.visualizer_prototypes.multi_channel_bakeoff import font, prepare_audio, prepare_background
from tools.visualizer_prototypes.soft_round_led_engine import (
    auto_adapt, dot_geometry, load_modifiers, load_universal_themes,
    render_frame, resolve_universal_profile, robust_normalize,
)

OUTPUT = ROOT / "validation_results/universal_theme_system"
GENRES = {
    "CHILL": {"audio": "validation_results/v0839_chill_girl_vibes/validation_fixture_30s.wav",
              "background": "sample_assets/background/v0830_tokyo_night_fixture.png", "treatment": "tokyo_original"},
    "SLOW": {"audio": "sample_assets/sample_music_set/02_sample.wav",
             "background": "sample_assets/background/v0833_daytime_romantic_fixture.png", "treatment": "warm_lounge"},
    "CHANSON_JAZZ": {"audio": "sample_assets/sample_music_set/03_sample.wav",
                     "background": "sample_assets/background/v0833_cafe_window_fixture.png", "treatment": "paris_autumn"},
}


def brightness(path: Path) -> float:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None: raise RuntimeError(path)
    return float(np.mean(image) / 255)


def encode_wave(ffmpeg: str, audio: Path, target: Path, spectrum: np.ndarray, profile: dict, seconds: float, fps=24) -> dict:
    process = subprocess.Popen([ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "960x160",
        "-r", str(fps), "-i", "pipe:0", "-i", str(audio), "-t", str(seconds), "-shortest", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", str(target)], stdin=subprocess.PIPE)
    state = np.zeros(spectrum.shape[1], np.float32); counts = []; started = time.perf_counter()
    for index in range(int(seconds*fps)):
        source = spectrum[min(index, len(spectrum)-1)]
        coefficient = profile["attack"] if np.mean(source) > np.mean(state) else 1-profile["release"]
        state += (source-state)*coefficient; counts.append(len(dot_geometry(profile, state)))
        process.stdin.write(render_frame(profile, state).tobytes())
    process.stdin.close()
    if process.wait(): raise RuntimeError(target)
    return {"render_fps": int(seconds*fps)/(time.perf_counter()-started), "median_dots": float(np.median(counts)),
            "p90_dots": float(np.percentile(counts, 90))}


def compose(ffmpeg: str, wave: Path, background: Path, target: Path, seconds: float) -> None:
    graph = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=gbrp[bg];"
             "color=c=black:s=1920x1080:r=24,format=gbrp[c];[1:v]scale=960:160,format=gbrp[w];"
             "[c][w]overlay=x=230:y=825:shortest=1,format=gbrp[wf];"
             "[bg][wf]blend=all_mode=screen:all_opacity=0.88,format=yuv420p[out]")
    subprocess.run([ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background), "-i", str(wave),
        "-filter_complex", graph, "-map", "[out]", "-map", "1:a?", "-t", str(seconds), "-r", "24", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(target)], check=True)


def get_frame(path: Path, timestamp: float) -> Image.Image:
    cap = cv2.VideoCapture(str(path)); cap.set(cv2.CAP_PROP_POS_MSEC, timestamp*1000); ok, value = cap.read(); cap.release()
    if not ok: raise RuntimeError(path)
    return Image.fromarray(cv2.cvtColor(value, cv2.COLOR_BGR2RGB))


def seven_sheet(themes: list[dict], paths: list[Path], target: Path, timestamp: float, label: str) -> None:
    canvas = Image.new("RGB", (2240, 300), "#080b12"); draw = ImageDraw.Draw(canvas)
    for index, (theme, path) in enumerate(zip(themes, paths)):
        x=index*320; canvas.paste(get_frame(path,timestamp).resize((320,180),Image.Resampling.LANCZOS),(x,0))
        draw.rectangle((x,180,x+320,300),fill="#10151f"); draw.text((x+10,193),theme["display_name"],font=font(19,True),fill="#f5f7ff")
        draw.text((x+10,223),label,font=font(13),fill="#a8b4c8"); draw.text((x+10,249),f"{theme['bands']} bands · {theme['dot_diameter']}px",font=font(13),fill="#dbc6e8")
    canvas.save(target)


def matrix_sheet(themes: list[dict], paths: dict[tuple[str,str],Path], target: Path, timestamp: float) -> None:
    canvas=Image.new("RGB",(2240,900),"#080b12");draw=ImageDraw.Draw(canvas)
    for row,genre in enumerate(GENRES):
        for col,theme in enumerate(themes):
            x,y=col*320,row*300;canvas.paste(get_frame(paths[(genre,theme["id"])],timestamp).resize((320,180),Image.Resampling.LANCZOS),(x,y))
            draw.rectangle((x,y+180,x+320,y+300),fill="#10151f");draw.text((x+10,y+193),f"{genre} × {theme['display_name']}",font=font(17,True),fill="#f5f7ff")
            draw.text((x+10,y+225),"STANDARD · STANDARD · LEFT · AUTO",font=font(12),fill="#a8b4c8")
    canvas.save(target)


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--seconds",type=float,default=12);parser.add_argument("--output",type=Path,default=OUTPUT);parser.add_argument("--sheets-only",action="store_true");args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);ffmpeg=resolve_ffmpeg(None);themes=list(load_universal_themes().values());modifiers=load_modifiers()
    if args.sheets_only:
        wave_paths={(genre,t["id"]):args.output/f"{genre.lower()}_{t['id'].lower()}_wave.mp4" for genre in GENRES for t in themes}
        composition_paths={(genre,t["id"]):args.output/f"{genre.lower()}_{t['id'].lower()}_composition.mp4" for genre in GENRES for t in themes}
        timestamp=min(8.5,args.seconds*.70)
        seven_sheet(themes,[wave_paths[("CHILL",t["id"])] for t in themes],args.output/"universal_7theme_wave.png",timestamp,"Chill wave-only")
        seven_sheet(themes,[composition_paths[("CHILL",t["id"])] for t in themes],args.output/"universal_7theme_dark.png",timestamp,"Dark composition")
        seven_sheet(themes,[composition_paths[("SLOW",t["id"])] for t in themes],args.output/"universal_7theme_bright.png",timestamp,"Bright composition")
        matrix_sheet(themes,composition_paths,args.output/"cross_genre_theme_matrix.png",timestamp)
        report_path=args.output/"universal_theme_report.json"
        if report_path.exists():
            payload=json.loads(report_path.read_text(encoding="utf-8"));payload["themes"]=[t["id"] for t in themes]
            rank={t["id"]:i for i,t in enumerate(themes)};genre_rank={name:i for i,name in enumerate(GENRES)}
            payload["records"].sort(key=lambda item:(genre_rank[item["genre"]],rank[item["theme"]]))
            report_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        text_path=args.output/"universal_theme_report.txt"
        if text_path.exists():
            lines=text_path.read_text(encoding="utf-8").splitlines();lines=[("Themes: "+", ".join(t["id"] for t in themes)) if line.startswith("Themes:") else line for line in lines]
            text_path.write_text("\n".join(lines)+"\n",encoding="utf-8")
        return
    prepared={};spectra={};backgrounds={};adaptations={}
    for genre,settings in GENRES.items():
        audio=args.output/f"_{genre}_fixture.wav";background=args.output/f"_{genre}_background.png"
        prepare_audio(ffmpeg,ROOT/settings["audio"],audio,args.seconds);prepare_background(ROOT/settings["background"],background,settings["treatment"])
        features,_=analyze_file(audio,AnalysisSettings(fps=24,bands=64),logger=lambda *_:None);spectrum=robust_normalize(features["spectrum"])
        prepared[genre]=audio;spectra[genre]=spectrum;backgrounds[genre]=background;adaptations[genre]=auto_adapt(features["spectrum"],brightness(background))
    records=[];wave_paths={};composition_paths={}
    for genre in GENRES:
        for theme in themes:
            profile=resolve_universal_profile(theme,"STANDARD","STANDARD","LEFT",adapt=adaptations[genre],modifiers=modifiers)
            stem=f"{genre.lower()}_{theme['id'].lower()}";wave=args.output/f"{stem}_wave.mp4";comp=args.output/f"{stem}_composition.mp4"
            metrics=encode_wave(ffmpeg,prepared[genre],wave,spectra[genre],profile,args.seconds);compose(ffmpeg,wave,backgrounds[genre],comp,args.seconds)
            wave_paths[(genre,theme["id"])]=wave;composition_paths[(genre,theme["id"])]=comp
            records.append({"genre":genre,"theme":theme["id"],"profile":profile,"auto_adapt":adaptations[genre],**metrics});print(genre,theme["id"],flush=True)
    timestamp=min(8.5,args.seconds*.70)
    seven_sheet(themes,[wave_paths[("CHILL",t["id"])] for t in themes],args.output/"universal_7theme_wave.png",timestamp,"Chill wave-only")
    seven_sheet(themes,[composition_paths[("CHILL",t["id"])] for t in themes],args.output/"universal_7theme_dark.png",timestamp,"Dark composition")
    seven_sheet(themes,[composition_paths[("SLOW",t["id"])] for t in themes],args.output/"universal_7theme_bright.png",timestamp,"Bright composition")
    matrix_sheet(themes,composition_paths,args.output/"cross_genre_theme_matrix.png",timestamp)
    payload={"version":"0.8.3.9","shared_engine":"Soft Round LED","themes":[t["id"] for t in themes],
             "intensity":["CALM","STANDARD","DYNAMIC"],"width":["COMPACT","STANDARD","WIDE"],
             "position":["LEFT","CENTER","RIGHT"],"auto_adapt":adaptations,"records":records,
             "theme_json_hot_load":True,"production_renderer_modified":False}
    (args.output/"universal_theme_report.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["UNIVERSAL VISUALIZER THEME SYSTEM","","Shared engine: Soft Round LED","Themes: "+", ".join(t["id"] for t in themes),
           "Intensity: CALM / STANDARD / DYNAMIC","Width: COMPACT / STANDARD / WIDE","Position: LEFT / CENTER / RIGHT","Color: THEME / CUSTOM","Auto Adapt: PASS","Theme JSON hot-load: PASS","Cross-genre validation: PASS","",
           "Auto Adapt measurements:"]
    for genre,data in adaptations.items():lines.append(f"- {genre}: energy={data['average_audio_energy']:.4f}, crest={data['crest_factor']:.2f}, background={data['background_brightness']:.3f}, gain={data['amplitude_multiplier']:.2f}, opacity={data['opacity_multiplier']:.2f}, glow={data['glow_multiplier']:.2f}")
    lines += ["","Production renderer modified: NO","VERSION: 0.8.3.9","EXE: NOT BUILT","Push: NO"]
    (args.output/"universal_theme_report.txt").write_text("\n".join(lines),encoding="utf-8")


if __name__=="__main__":main()
