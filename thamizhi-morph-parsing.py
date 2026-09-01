#!/usr/bin/env python3
"""Compatibility launcher for the former monolithic script.

Install the package and use ``thamizhi-morph analyze`` directly in new integrations.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from thamizhi_morph.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["analyze", *sys.argv[1:]]))
