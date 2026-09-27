import json
from pathlib import Path

import pytest

from visualizers.schema import WaveformValidationError, new_waveform, validate_waveform
from visualizers.user_profiles import UserWaveformStore


ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "validation_results" / "v0840_user_waveform_tests"


def store():
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    for path in TEST_DIR.glob("*.mwswave"): path.unlink()
    return UserWaveformStore(TEST_DIR, {"soft_round_led"})


def test_save_reload_duplicate_rename_delete():
    target = store(); first = target.save(new_waveform("Tokyo Pink Night", theme="NEON", intensity="DYNAMIC"))
    assert target.load(first)["intensity"] == "DYNAMIC"
    duplicate = target.duplicate(first); assert duplicate != first and duplicate.exists()
    renamed = target.rename(duplicate, "Tokyo Pink Night 02"); assert renamed.exists()
    target.delete(renamed); assert not renamed.exists()


def test_export_import_roundtrip():
    target = store(); source = target.save(new_waveform("Warm Gold", theme="WARM"))
    exported = target.export_file(source, TEST_DIR / "shared")
    source.unlink(); imported, warnings = target.import_file(exported)
    assert not warnings and target.load(imported)["theme"] == "WARM"


def test_invalid_json_malicious_and_unknown_family_rejected():
    target = store(); invalid = TEST_DIR / "invalid.mwswave"; invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError): target.import_file(invalid)
    malicious = new_waveform("Bad"); malicious["script"] = "Remove-Item C:/"
    with pytest.raises(WaveformValidationError): validate_waveform(malicious, {"soft_round_led"})
    unknown = new_waveform("Unknown"); unknown["renderer_family"] = "particles"
    with pytest.raises(WaveformValidationError, match="지원되지 않습니다"): validate_waveform(unknown, {"soft_round_led"})


def test_unknown_fields_are_ignored_with_warning():
    data = new_waveform("Safe"); data["future_metadata"] = {"label": "ok"}
    clean, warnings = validate_waveform(data, {"soft_round_led"})
    assert "future_metadata" not in clean and warnings
