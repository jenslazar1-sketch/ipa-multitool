"""Pull the provisioning profile and signing certificate(s) out of an IPA.

Works on a local .ipa or an http(s) URL (downloaded first). Only PUBLIC
certificates and the embedded profile can be recovered -- an IPA never
contains the signer's private key.
"""
from __future__ import annotations
import zipfile, plistlib
from pathlib import Path
from . import profile as prof_mod, certs as certs_mod
from .util import ToolError, info, ok, warn, resolve_ipa, tempdir


def _read_ipa_member(zf: zipfile.ZipFile, suffix: str) -> tuple[str, bytes] | None:
    for n in zf.namelist():
        if n.endswith(suffix) and "/Payload/" in ("/" + n):
            return n, zf.read(n)
    for n in zf.namelist():                                  # looser fallback
        if n.endswith(suffix):
            return n, zf.read(n)
    return None


def _app_executable_name(zf: zipfile.ZipFile) -> str | None:
    for n in zf.namelist():
        if n.endswith(".app/Info.plist"):
            try:
                data = plistlib.loads(zf.read(n))
                exe = data.get("CFBundleExecutable")
                if exe:
                    return n[:n.rfind("/") + 1] + exe        # Payload/X.app/<exe>
            except Exception:
                pass
    return None


def pull(path_or_url: str, out_dir: str, *, dump_chain: bool = True) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with tempdir() as tmp:
        ipa = resolve_ipa(path_or_url, tmp)
        stem = ipa.stem
        with zipfile.ZipFile(ipa) as zf:
            # 1) embedded.mobileprovision
            got = _read_ipa_member(zf, "embedded.mobileprovision")
            if got:
                _, raw = got
                mp_path = out / f"{stem}.mobileprovision"
                mp_path.write_bytes(raw)
                ok(f"profile  -> {mp_path}")
                try:
                    prof = prof_mod.load(mp_path)
                    print()
                    for k, v in prof_mod.summary(prof):
                        print(f"    {k:22} {v}")
                    print()
                    # certs authorized by the profile
                    for i, der in enumerate(prof_mod.developer_cert_ders(prof)):
                        cert = certs_mod.cert_from_der(der)
                        cp = out / f"{stem}.profile-cert{i}.pem"
                        cp.write_bytes(certs_mod.to_pem(cert))
                        ok(f"profile cert #{i} -> {cp}")
                except Exception as e:
                    warn(f"could not parse profile: {e}")
            else:
                warn("no embedded.mobileprovision (App Store IPAs are stripped of it)")

            # 2) signing cert chain from the main Mach-O
            exe_member = _app_executable_name(zf)
            if exe_member and dump_chain:
                exe_bytes = zf.read(exe_member)
                exe_tmp = Path(tmp) / "mainexe"
                exe_tmp.write_bytes(exe_bytes)
                try:
                    chain = certs_mod.certs_from_macho(exe_tmp)
                except ToolError as e:
                    warn(str(e)); chain = []
                if chain:
                    info(f"signing certificate chain ({len(chain)} cert(s)) from {exe_member}:")
                    for i, cert in enumerate(chain):
                        cp = out / f"{stem}.signer{i}.pem"
                        cp.write_bytes(certs_mod.to_pem(cert))
                        print()
                        for k, v in certs_mod.cert_summary(cert):
                            print(f"    {k:22} {v}")
                        ok(f"signer cert #{i} -> {cp}")
                else:
                    warn("no code-signature certificates found (unsigned or fakesigned binary)")
            elif not exe_member:
                warn("could not locate the app's main executable")

    print()
    warn("Reminder: these are PUBLIC certs + the profile only. The private "
         "signing key is NOT inside an IPA and cannot be extracted.")
