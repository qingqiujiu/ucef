#!/usr/bin/env python3
"""Initialize a .ucef workspace in the current project without overwriting files."""
from pathlib import Path
import shutil
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_DIR / "templates"
PROJECT = Path.cwd()
WS = PROJECT / ".ucef"

for d in [
    WS,
    WS / "scenarios",
    WS / "work_units" / "pending",
    WS / "work_units" / "completed",
    WS / "contexts",
    WS / "runs",
    WS / "metadata",
]:
    d.mkdir(parents=True, exist_ok=True)

copies = [
    (TEMPLATES / "config.yaml", WS / "config.yaml"),
    (TEMPLATES / "scenario.yaml", WS / "scenarios" / "scenario.example.yaml"),
    (TEMPLATES / "work_unit.yaml", WS / "work_units" / "work_unit.example.yaml"),
    (TEMPLATES / "metadata.example.yaml", WS / "metadata" / "metadata.example.yaml"),
]
created, skipped = [], []
for src, dst in copies:
    if not src.exists():
        continue
    if dst.exists():
        skipped.append(str(dst))
    else:
        shutil.copy2(src, dst)
        created.append(str(dst))

overrides = WS / "overrides.json"
if overrides.exists():
    skipped.append(str(overrides))
else:
    overrides.write_text('{"version": 1, "entities": {}}\n', encoding="utf-8")
    created.append(str(overrides))

sys.path.insert(0, str(SKILL_DIR / "runtime"))
from ucef.cli import main
rc = main(["--config", str(WS / "config.yaml"), "init"])

print("\nUCEF workspace ready:", WS)
if created:
    print("Created:")
    for x in created:
        print("  +", x)
if skipped:
    print("Kept existing:")
    for x in skipped:
        print("  =", x)
raise SystemExit(rc or 0)
