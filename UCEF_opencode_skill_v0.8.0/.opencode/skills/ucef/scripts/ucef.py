#!/usr/bin/env python3
"""Run the UCEF Lite runtime bundled inside this OpenCode skill."""
from pathlib import Path
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = SKILL_DIR / "runtime"
sys.path.insert(0, str(RUNTIME_DIR))

from ucef.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
