#!/usr/bin/env python3
"""Entry point for running from source and for PyInstaller packaging."""
import sys
from ipatool.cli import main

if __name__ == "__main__":
    sys.exit(main())
