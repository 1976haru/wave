from __future__ import annotations

import json
import os
import re
import shutil
from copy import deepcopy
from pathlib import Path
from core.runtime_paths import app_data_root

from .schema import WaveformValidationError, new_waveform, validate_waveform


def default_waveform_dir() -> Path:
    return app_data_root() / "waveforms"


def safe_filename(name: str) -> str:
    value = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name.strip()).strip("._")
    return (value or "My_Waveform")[:80]


class UserWaveformStore:
    def __init__(self, directory: str | Path | None = None, installed_families: set[str] | None = None):
        self.directory = Path(directory) if directory else default_waveform_dir()
        self.installed_families = installed_families or {"soft_round_led"}
        if directory is None:self._migrate_legacy()

    def _migrate_legacy(self):
        roaming=os.environ.get("APPDATA")
        legacy=Path(roaming)/"MusicWaveStudio"/"waveforms" if roaming else None
        if not legacy or not legacy.is_dir() or legacy.resolve()==self.directory.resolve():return
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            for source in legacy.glob("*.mwswave"):
                target=self.directory/source.name
                if not target.exists():shutil.copy2(source,target)
        except OSError:
            pass

    def _ensure(self):
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[tuple[Path, dict]]:
        self._ensure(); result = []
        for path in sorted(self.directory.glob("*.mwswave"), key=lambda item: item.name.lower()):
            try: result.append((path, self.load(path)))
            except (OSError, json.JSONDecodeError, WaveformValidationError): continue
        return result

    def load(self, path: str | Path) -> dict:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_waveform(raw, self.installed_families)[0]

    def save(self, waveform: dict, overwrite: bool = True) -> Path:
        clean, _ = validate_waveform(waveform, self.installed_families); self._ensure()
        target = self.directory / f"{safe_filename(clean['name'])}.mwswave"
        if target.exists() and not overwrite:
            index = 2
            while (self.directory / f"{safe_filename(clean['name'])}_{index}.mwswave").exists(): index += 1
            target = self.directory / f"{safe_filename(clean['name'])}_{index}.mwswave"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target); return target

    def import_file(self, source: str | Path) -> tuple[Path, list[str]]:
        source = Path(source)
        if source.suffix.lower() != ".mwswave" or source.stat().st_size > 128 * 1024:
            raise WaveformValidationError("Invalid or oversized .mwswave package.")
        raw = json.loads(source.read_text(encoding="utf-8")); clean, warnings = validate_waveform(raw, self.installed_families)
        return self.save(clean, overwrite=False), warnings

    def export_file(self, source: str | Path, target: str | Path) -> Path:
        clean = self.load(source); destination = Path(target)
        if destination.suffix.lower() != ".mwswave": destination = destination.with_suffix(".mwswave")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    def delete(self, source: str | Path) -> None:
        path = Path(source).resolve()
        if path.parent != self.directory.resolve() or path.suffix.lower() != ".mwswave":
            raise WaveformValidationError("Refusing to delete a file outside My Waveforms.")
        path.unlink(missing_ok=True)

    def rename(self, source: str | Path, name: str) -> Path:
        waveform = self.load(source); self.delete(source); waveform["name"] = name
        return self.save(waveform, overwrite=False)

    def duplicate(self, source: str | Path, name: str | None = None) -> Path:
        waveform = deepcopy(self.load(source)); waveform["name"] = name or f"{waveform['name']} Copy"
        return self.save(waveform, overwrite=False)
