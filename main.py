#!/usr/bin/env python3
"""Tenký wrapper pro spuštění Aether Downloader (desktop i web režim)."""

import sys

from stahovac.__main__ import run

if __name__ == "__main__":
    sys.exit(run())
