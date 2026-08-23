#!/usr/bin/env python3
"""Compatibility entrypoint. It never initializes inside the current Java project implicitly."""

from init_workspace import run


if __name__ == "__main__":
    raise SystemExit(run())
