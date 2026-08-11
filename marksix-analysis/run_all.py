#!/usr/bin/env python3
"""Fetch public Mark Six history, then run statistical analysis."""

from __future__ import annotations

import sys

from analyze import main as analyze_main
from fetch_data import main as fetch_main


def main() -> int:
    code = fetch_main([])
    if code != 0:
        return code
    return analyze_main([])


if __name__ == "__main__":
    sys.exit(main())
