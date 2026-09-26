from pathlib import Path

import numpy as np

from tools.visualizer_prototypes.prototype_runner import STYLES, render_style


ROOT = Path(__file__).resolve().parents[1]


def test_research_does_not_bump_production_version():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == "0.8.3.9"


def test_twelve_distinct_styles_and_three_reference_matches():
    assert len(STYLES) == 12
    assert len({slug for slug, _ in STYLES}) == 12
    names = [name for _, name in STYLES]
    assert sum("Reference R" in name for name in names) == 3


def test_prototype_frames_are_visually_distinct():
    values = np.linspace(.08, .96, 64, dtype=np.float32)
    frames = [render_style(style, values, .75, 7.0) for style in range(1, 13)]
    assert all(frame.shape == (160, 960, 3) for frame in frames)
    # Downsampled fingerprints ensure these are different geometries rather
    # than twelve palette aliases of one renderer.
    fingerprints = {frame[::8, ::8].tobytes() for frame in frames}
    assert len(fingerprints) == 12


def test_required_survey_artifacts_exist():
    survey = ROOT / "research/visualizer_survey"
    for name in (
        "visualizer_library_matrix.csv",
        "visualizer_library_matrix.json",
        "visualizer_library_matrix.md",
        "shortlist_top25.md",
        "shortlist_tokyo15.md",
        "library_reference_top20_01.png",
        "library_reference_top20_02.png",
        "FINAL_VISUALIZER_SURVEY.md",
    ):
        assert (survey / name).is_file(), name
