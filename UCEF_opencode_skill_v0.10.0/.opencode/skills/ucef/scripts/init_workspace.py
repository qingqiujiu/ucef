#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_ROOT / "templates"
sys.path.insert(0, str(SKILL_ROOT / "runtime"))

from ucef.cli import main as ucef_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize an independent UCEF analysis workspace")
    parser.add_argument("--workspace", required=True, help="Directory outside all Java project trees")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SOURCE_ID=ABSOLUTE_PATH",
        help="Optionally register one read-only Java project; repeat for more projects",
    )
    return parser


def parse_source(value: str) -> tuple[str, str]:
    source_id, separator, path = value.partition("=")
    if not separator or not source_id or not path:
        raise ValueError(f"Invalid --source {value!r}; expected SOURCE_ID=ABSOLUTE_PATH")
    return source_id, path


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    for directory in (
        workspace / "scenarios",
        workspace / "work_units" / "pending",
        workspace / "work_units" / "completed",
        workspace / "contexts",
        workspace / "runs",
        workspace / "site",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    copies = (
        (TEMPLATES / "config.json", workspace / "workspace.json"),
        (TEMPLATES / "sources.json", workspace / "sources.json"),
        (TEMPLATES / "scenario.json", workspace / "scenarios" / "scenario.example.json"),
        (TEMPLATES / "direct_plan.example.json", workspace / "runs" / "direct_plan.example.json"),
        (TEMPLATES / "direct_block.example.json", workspace / "runs" / "direct_block.example.json"),
        (TEMPLATES / "direct_overview.example.json", workspace / "runs" / "direct_overview.example.json"),
    )
    created, kept = [], []
    for source, target in copies:
        if target.exists():
            kept.append(str(target))
        else:
            shutil.copy2(source, target)
            created.append(str(target))

    result = ucef_main(["--workspace", str(workspace), "init"])
    if result:
        return result
    for source_arg in args.source:
        source_id, source_path = parse_source(source_arg)
        result = ucef_main([
            "--workspace", str(workspace), "source-add",
            "--source-id", source_id, "--path", source_path,
        ])
        if result:
            return result

    print("UCEF analysis workspace:", workspace)
    for path in created:
        print("  +", path)
    for path in kept:
        print("  =", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
