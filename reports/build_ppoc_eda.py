#!/usr/bin/env python3
"""Entry point for the project-neutral PPOC EDA report.

    uv run python reports/build_ppoc_eda.py --help
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ppoc_eda.build import main

if __name__ == "__main__":
    raise SystemExit(main())
