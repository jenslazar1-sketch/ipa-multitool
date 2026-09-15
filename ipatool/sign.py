"""Re-sign an IPA using zsign."""
from __future__ import annotations
from pathlib import Path
from . import bins
from .util import run, info, ok, ToolError


def sign_ipa(
    ipa: str,
    output: str,
    *,
    p12: str | None = None,
    password: str | None = None,
    key: str | None = None,
    cert: str | None = None,
    prov: str | None = None,
    bundle_id: str | None = None,
    name: str | None = None,
    version: str | None = None,
    entitlements: str | None = None,
    dylibs: list[str] | None = None,
    weak: bool = False,
    zip_level: int = 9,
    install: bool = False,
    quiet: bool = False,
) -> str:
    zsign = bins.require("zsign")
    if not (p12 or key):
        raise ToolError("provide --p12 (or --key/--cert) to sign")
    if not prov:
        raise ToolError("provide --prov (a .mobileprovision matching the certificate)")

    cmd = [zsign]
    if p12:
        cmd += ["-k", p12]
    else:
        cmd += ["-k", key]
        if cert:
            cmd += ["-c", cert]
    if password is not None:
        cmd += ["-p", password]
    cmd += ["-m", prov]
    if bundle_id:  cmd += ["-b", bundle_id]
    if name:       cmd += ["-n", name]
    if version:    cmd += ["-r", version]
    if entitlements: cmd += ["-e", entitlements]
    for d in (dylibs or []):
        cmd += (["-w"] if weak else []) + ["-l", d]
    if quiet:      cmd += ["-q"]
    if install:    cmd += ["-i"]
    cmd += ["-z", str(zip_level), "-o", output, ipa]

    info("signing: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    run(cmd)
    out = Path(output)
    if out.is_file():
        ok(f"signed IPA -> {out}  ({out.stat().st_size >> 20} MiB)")
    return output
