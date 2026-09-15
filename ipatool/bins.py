"""Locate external binaries (zsign, ldid, libimobiledevice tools).

Search order: a ./bin folder next to the ipatool executable (how the packaged
release ships them), the PyInstaller bundle dir, then the system PATH.
"""
from __future__ import annotations
import os, sys, shutil
from pathlib import Path
from .util import ToolError


def _search_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):                      # packaged .exe
        dirs.append(Path(sys.executable).resolve().parent / "bin")
        dirs.append(Path(sys.executable).resolve().parent)
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        dirs.append(Path(meipass) / "bin")
    here = Path(__file__).resolve().parent.parent           # repo root when run from source
    dirs.append(here / "bin")
    return dirs


def find(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    for d in _search_dirs():
        for cand in (d / exe, d / name):
            if cand.is_file():
                return str(cand)
    return shutil.which(name) or shutil.which(exe)


HINTS = {
    "zsign": "Get it from the GitHub Actions release bundle, or build https://github.com/zhlynn/zsign",
    "ldid": "Get it from the release bundle, or build https://github.com/ProcursusTeam/ldid",
    "ideviceinstaller": "Install libimobiledevice (imobiledevice-net / libimobiledevice-win)",
    "idevice_id": "Install libimobiledevice",
    "ideviceinfo": "Install libimobiledevice",
}


def require(name: str) -> str:
    p = find(name)
    if not p:
        raise ToolError(f"'{name}' not found. {HINTS.get(name, '')}".strip())
    return p


def status() -> dict[str, str | None]:
    return {n: find(n) for n in ("zsign", "ldid", "ideviceinstaller", "idevice_id", "ideviceinfo")}
