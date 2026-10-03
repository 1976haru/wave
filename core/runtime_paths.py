from __future__ import annotations

import os
from pathlib import Path


APP_DIR_NAME = "MusicWaveStudio"


def app_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / ".music_wave_studio"


def state_dir() -> Path:
    return app_data_root() / "state"


def cache_dir() -> Path:
    return app_data_root() / "cache"


def logs_dir() -> Path:
    return app_data_root() / "logs"


def user_templates_dir() -> Path:
    return app_data_root() / "templates"


def queue_state_path() -> Path:
    return state_dir() / "queue_state.json"


def running_marker_path() -> Path:
    return state_dir() / "running.lock"


def instance_lock_path() -> Path:
    return state_dir() / "instance.lock"
