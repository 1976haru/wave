from __future__ import annotations

import re
from copy import deepcopy

FORMAT = "MusicWaveStudioWaveform"
FORMAT_VERSION = 1
THEMES = {"NEON", "WARM", "ELEGANT", "SOFT", "ENERGETIC", "MONO", "CUSTOM"}
INTENSITIES = {"CALM", "STANDARD", "DYNAMIC"}
WIDTHS = {"COMPACT", "STANDARD", "WIDE"}
POSITIONS = {"LEFT", "CENTER", "RIGHT"}
COLOR_MODES = {"THEME", "CUSTOM"}
SIGNATURE_VARIANTS = {"MIDNIGHT_PULSE", "SILK_WAVE", "TWO_HEARTS"}
SIGNATURE_MOTIONS = {"CALM", "STANDARD", "DYNAMIC", "VERY_DYNAMIC"}
SIGNATURE_VERTICAL = {"TOP", "CENTER", "BOTTOM"}
SIGNATURE_PRESENCE = {"SOFT", "DEFAULT", "CRISP"}
MORNING_SHAPES = {"MORNING_HALO", "PEARL_HALO", "TWIN_HALO", "BREATHING_RING", "SUNRISE_ARC", "SOFT_OVAL", "VERTICAL_OVAL", "ROUND_SQUARE", "PEARL_SQUARE", "SOFT_DIAMOND", "HEART_WHISPER", "PEARL_HEART", "SOFT_CAPSULE", "CLOUD_LOOP", "PETAL_LOOP", "FLOWER_HALO", "RIBBON_ORBIT", "STEREO_ORBIT", "DOTTED_ORBIT", "CAFE_FRAME"}
ADVANCED_FIELDS = {
    "bands": (8, 128), "dot_diameter": (2.0, 10.0), "horizontal_gap": (2.0, 30.0),
    "vertical_gap": (2.0, 16.0), "amplitude_gain": (.25, 2.0), "attack": (.02, .95),
    "release": (.50, .99), "temporal_smoothing": (0, 8), "glow_strength": (0, 2),
    "glow_radius": (.5, 8), "overall_opacity": (.1, 1.5), "brightness_compensation": (.5, 1.8),
    "min_frequency": (20, 400), "max_frequency": (2000, 22000), "low_band_weight": (.2, 2),
    "mid_band_weight": (.2, 2), "high_band_weight": (.1, 2), "tail_threshold": (0, .8),
    "x_offset": (-480, 480), "y_offset": (-100, 100), "background_brightness": (0, 1),
}
FORBIDDEN_KEYS = {"code", "python", "javascript", "script", "command", "shell", "executable", "dll", "url", "import"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class WaveformValidationError(ValueError):
    pass


def _contains_forbidden(value) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower() in FORBIDDEN_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def validate_waveform(data: dict, installed_families: set[str] | None = None) -> tuple[dict, list[str]]:
    if not isinstance(data, dict) or _contains_forbidden(data):
        raise WaveformValidationError("Waveform package contains an unsafe field.")
    if data.get("format") != FORMAT or data.get("format_version") != FORMAT_VERSION:
        raise WaveformValidationError("Unsupported .mwswave format or version.")
    family = str(data.get("renderer_family", "")).lower()
    if installed_families is not None and family not in installed_families:
        raise WaveformValidationError("이 파형은 현재 설치된 Renderer Family에서 지원되지 않습니다.")
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 80:
        raise WaveformValidationError("Waveform name must contain 1-80 characters.")
    theme = str(data.get("theme", "NEON")).upper()
    intensity = str(data.get("intensity", "STANDARD")).upper()
    width = str(data.get("width", "STANDARD")).upper()
    position = str(data.get("position", "LEFT")).upper()
    color_mode = str(data.get("color_mode", "THEME")).upper()
    if theme not in THEMES or intensity not in INTENSITIES or width not in WIDTHS or position not in POSITIONS or color_mode not in COLOR_MODES:
        raise WaveformValidationError("Waveform contains an unsupported option.")
    colors = data.get("colors", [])
    if color_mode == "CUSTOM" and (not isinstance(colors, list) or not 2 <= len(colors) <= 4 or not all(HEX.match(str(c)) for c in colors)):
        raise WaveformValidationError("Custom color mode requires 2-4 #RRGGBB colors.")
    advanced = data.get("advanced", {})
    if not isinstance(advanced, dict):
        raise WaveformValidationError("Advanced settings must be a JSON object.")
    clean_advanced = {}
    warnings = []
    for key, value in advanced.items():
        if key not in ADVANCED_FIELDS:
            warnings.append(f"Ignored advanced field: {key}")
            continue
        low, high = ADVANCED_FIELDS[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not low <= float(value) <= high:
            raise WaveformValidationError(f"Advanced value out of range: {key}")
        clean_advanced[key] = int(value) if key in {"bands", "temporal_smoothing"} else float(value)
    signature = data.get("signature", {})
    if family == "tokyo_signature":
        if not isinstance(signature, dict): raise WaveformValidationError("Signature settings must be a JSON object.")
        variant=str(signature.get("variant","MIDNIGHT_PULSE")).upper();motion=str(signature.get("motion","DYNAMIC")).upper();vertical=str(signature.get("vertical_position","BOTTOM")).upper();presence=str(signature.get("presence","CRISP")).upper();size=float(signature.get("size",1.0))
        if variant not in SIGNATURE_VARIANTS or motion not in SIGNATURE_MOTIONS or vertical not in SIGNATURE_VERTICAL or presence not in SIGNATURE_PRESENCE or not .7<=size<=1.3:raise WaveformValidationError("Unsupported Tokyo Signature option.")
        signature={"variant":variant,"motion":motion,"size":size,"vertical_position":vertical,"horizontal_position":position,"presence":presence,"auto_adapt":bool(signature.get("auto_adapt",True)),"local_adapt":bool(signature.get("local_adapt",True)),"colors":[str(c).upper() for c in signature.get("colors",[]) if HEX.match(str(c))]}
    morning = data.get("morning_shape", {})
    if family == "morning_shape":
        if not isinstance(morning, dict): raise WaveformValidationError("Morning Shape settings must be a JSON object.")
        shape_id=str(morning.get("shape_id","MORNING_HALO")).upper();movement=str(morning.get("movement","CALM")).upper();mode=str(morning.get("color_mode","SOLID")).upper();stroke=str(morning.get("stroke_style","THIN")).upper();glow=str(morning.get("glow_level","SUBTLE")).upper()
        color_a=str(morning.get("color_a","#FFF8EC")).upper();color_b=str(morning.get("color_b","#FFCDB6")).upper();size=float(morning.get("shape_size",1));x=float(morning.get("position_x",.5));y=float(morning.get("position_y",.5));response=float(morning.get("response_strength",1));opacity=float(morning.get("opacity",.88))
        if shape_id not in MORNING_SHAPES or movement not in {"CALM","STANDARD","LIVELY"} or mode not in {"SOLID","GRADIENT"} or stroke not in {"THIN","DEFAULT","THICK"} or glow not in {"NONE","SUBTLE","DEFAULT"} or not HEX.match(color_a) or not HEX.match(color_b) or not .5<=size<=2 or not .05<=x<=.95 or not .05<=y<=.95 or not .25<=response<=2 or not .4<=opacity<=1:raise WaveformValidationError("Unsupported Morning Shape option.")
        morning={"shape_id":shape_id,"shape_size":size,"position_x":x,"position_y":y,"movement":movement,"response_strength":response,"color_mode":mode,"color_a":color_a,"color_b":color_b,"opacity":opacity,"stroke_style":stroke,"glow_level":glow,"local_adapt":bool(morning.get("local_adapt",True))}
    known = {"format", "format_version", "name", "description", "renderer_family", "theme", "intensity", "width", "position", "color_mode", "colors", "auto_adapt", "local_adapt", "advanced", "signature", "morning_shape"}
    warnings += [f"Ignored field: {key}" for key in data if key not in known]
    clean = {"format": FORMAT, "format_version": FORMAT_VERSION, "name": name,
             "description": str(data.get("description", ""))[:500], "renderer_family": family,
             "theme": theme, "intensity": intensity, "width": width, "position": position,
             "color_mode": color_mode, "colors": [str(c).upper() for c in colors] if color_mode == "CUSTOM" else [],
             "auto_adapt": bool(data.get("auto_adapt", True)), "local_adapt": bool(data.get("local_adapt", True)), "advanced": clean_advanced}
    if family == "tokyo_signature": clean["signature"] = signature
    if family == "morning_shape": clean["morning_shape"] = morning
    return clean, warnings


def new_waveform(name: str, **values) -> dict:
    data = {"format": FORMAT, "format_version": FORMAT_VERSION, "name": name, "description": "",
            "renderer_family": "soft_round_led", "theme": "NEON", "intensity": "STANDARD",
            "width": "STANDARD", "position": "LEFT", "color_mode": "THEME", "colors": [],
            "auto_adapt": True, "local_adapt": True, "advanced": {}}
    data.update(deepcopy(values))
    return validate_waveform(data, {"soft_round_led", "tokyo_signature", "morning_shape"})[0]
