#!/usr/bin/env python3
"""Entry point for the ipatool GUI (used when packaging with PyInstaller --windowed)."""
import sys
from ipatool.gui import main

if __name__ == "__main__":
    sys.exit(main() or 0)
