"""Ad-hoc 'fakesign' an IPA with ldid, for jailbroken devices (AppSync)."""
from __future__ import annotations
import zipfile, shutil, stat, os
from pathlib import Path
from . import bins, plist_edit
from .util import run, info, ok, ToolError, tempdir, find_app_dir


def _macho_files(app_dir: Path):
    """Yield Mach-O files in the bundle (main exe, dylibs, frameworks, plugins)."""
    exe_name = None
    ip = app_dir / "Info.plist"
    if ip.is_file():
        try:
            exe_name = plist_edit.load(ip).get("CFBundleExecutable")
        except Exception:
            pass
    seen = set()
    if exe_name and (app_dir / exe_name).is_file():
        seen.add(app_dir / exe_name); yield app_dir / exe_name
    for pat in ("*.dylib", "**/*.dylib", "Frameworks/*.framework/*", "PlugIns/*.appex/*"):
        for f in app_dir.glob(pat):
            if f.is_file() and f not in seen:
                with open(f, "rb") as fh:
                    magic = fh.read(4)
                if magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
                    seen.add(f); yield f


def fakesign_ipa(ipa: str, output: str, *, entitlements: str | None = None, zip_level: int = 9) -> str:
    ldid = bins.require("ldid")
    with tempdir() as tmp:
        info(f"extracting {ipa}")
        with zipfile.ZipFile(ipa) as zf:
            zf.extractall(tmp)
        app = find_app_dir(Path(tmp))
        n = 0
        for macho in _macho_files(app):
            args = [ldid, f"-S{entitlements}" if entitlements else "-S", str(macho)]
            run(args)
            n += 1
        ok(f"fakesigned {n} Mach-O file(s)")
        out = Path(output)
        if out.exists():
            out.unlink()
        info(f"repacking -> {out}")
        _zip_dir(Path(tmp), out, zip_level)
    ok(f"fakesigned IPA -> {output}")
    return output


def _zip_dir(root: Path, out: Path, level: int) -> None:
    payload = root / "Payload"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
        for f in sorted(payload.rglob("*")):
            zf.write(f, f.relative_to(root).as_posix())
