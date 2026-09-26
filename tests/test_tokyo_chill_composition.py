from pathlib import Path

from tools import build_wave_ab_validation as review


def test_local_backgrounds_and_stable_presets_exist():
    assert set(review.PRESETS) == {"HIS", "DUAL", "HER"}
    assert set(review.BACKGROUNDS) == {"bright", "mid", "dark"}
    assert all(path.exists() for path in review.BACKGROUNDS.values())
    assert review.OPACITY["bright"] > review.OPACITY["mid"] > review.OPACITY["dark"]


def test_composition_command_contract(monkeypatch):
    captured = []
    monkeypatch.setattr(review, "run", lambda command: captured.append(command))
    review.compose("ffmpeg", Path("wave.mp4"), Path("background.png"), Path("output.mp4"), 24, .86)
    command = captured[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "1920:1080" in graph
    assert "scale=960:160" in graph
    assert "overlay=x=480:y=800" in graph
    assert "all_mode=screen" in graph
    assert command[command.index("-r") + 1] == "24"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
