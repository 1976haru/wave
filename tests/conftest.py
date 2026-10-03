import os

import pytest

# The suite exercises render/analysis paths with monkeypatched decoders, so it runs
# in-process by default; memory saver (isolated analysis) is covered explicitly in
# tests/test_v0854_low_memory_mode.py.
os.environ.setdefault("MWS_MEMORY_SAVER", "0")


@pytest.fixture(autouse=True)
def _reset_memory_saver():
    # MainWindow restores the persisted toggle (default ON); keep it per-test.
    yield
    from core import memory_mode
    memory_mode.set_enabled(os.environ.get("MWS_MEMORY_SAVER", "0") != "0")
