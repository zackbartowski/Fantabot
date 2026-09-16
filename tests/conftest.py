from __future__ import annotations

import sys
from pathlib import Path

# Permette `import app...` eseguendo pytest dalla root del progetto.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")
