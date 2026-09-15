"""Device operations over USB via libimobiledevice (optional dependency)."""
from __future__ import annotations
from . import bins
from .util import run, info, ok, warn


def udids() -> list[str]:
    idev = bins.require("idevice_id")
    out = run([idev, "-l"], capture=True).stdout.strip()
    return [l.strip() for l in out.splitlines() if l.strip()]


def device_info() -> None:
    ids = udids()
    if not ids:
        warn("no device detected over USB"); return
    ok(f"{len(ids)} device(s): {', '.join(ids)}")
    info_bin = bins.find("ideviceinfo")
    if info_bin:
        for key in ("DeviceName", "ProductType", "ProductVersion", "UniqueDeviceID"):
            r = run([info_bin, "-k", key], capture=True, check=False)
            if r.returncode == 0:
                print(f"    {key:16} {r.stdout.strip()}")


def install(ipa: str) -> None:
    inst = bins.require("ideviceinstaller")
    info(f"installing {ipa}")
    run([inst, "-i", ipa])
    ok("installed")


def list_apps() -> None:
    inst = bins.require("ideviceinstaller")
    run([inst, "-l"])
