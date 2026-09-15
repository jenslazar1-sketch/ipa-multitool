"""Info.plist read/patch helpers (handles both binary and XML plists)."""
from __future__ import annotations
import plistlib
from pathlib import Path
from .util import ToolError


def load(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ToolError(f"plist not found: {p}")
    with open(p, "rb") as f:
        return plistlib.load(f)


def save(path: str | Path, data: dict, *, binary: bool = True) -> None:
    fmt = plistlib.FMT_BINARY if binary else plistlib.FMT_XML
    with open(path, "wb") as f:
        plistlib.dump(data, f, fmt=fmt)


def _coerce(value: str):
    low = value.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if value.isdigit():
        return int(value)
    return value


def patch(path: str | Path, changes: dict[str, str]) -> dict:
    """Apply KEY=VALUE changes (values coerced to bool/int where obvious)."""
    data = load(path)
    for k, v in changes.items():
        data[k] = _coerce(v)
    # keep the original binary/xml-ness: re-detect
    with open(path, "rb") as f:
        head = f.read(8)
    save(path, data, binary=head.startswith(b"bplist"))
    return data


SUMMARY_KEYS = [
    ("CFBundleIdentifier", "Bundle ID"),
    ("CFBundleDisplayName", "Display name"),
    ("CFBundleName", "Name"),
    ("CFBundleShortVersionString", "Version"),
    ("CFBundleVersion", "Build"),
    ("MinimumOSVersion", "Min iOS"),
    ("CFBundleExecutable", "Executable"),
]


def summary(data: dict) -> list[tuple[str, str]]:
    out = []
    for key, label in SUMMARY_KEYS:
        if key in data:
            out.append((label, str(data[key])))
    return out
