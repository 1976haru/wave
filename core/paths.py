from __future__ import annotations
import sys
from pathlib import Path
def resource_path(relative):return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[1]))/relative
