"""ipatool command-line interface."""
from __future__ import annotations
import argparse, sys, zipfile, plistlib
from pathlib import Path

from . import __version__, bins, sign as sign_mod, fakesign as fakesign_mod
from . import certs as certs_mod, profile as prof_mod, plist_edit, device, extract
from .util import ToolError, info, ok, warn, err, tempdir, resolve_ipa


def _table(rows):
    for k, v in rows:
        print(f"    {k:22} {v}")


# ---------------- commands ----------------

def cmd_doctor(a):
    print(f"ipatool {__version__}\n")
    st = bins.status()
    for name, path in st.items():
        mark = "OK " if path else "-- "
        print(f"  [{mark}] {name:18} {path or '(not found)'}")
    missing = [n for n, p in st.items() if not p]
    print()
    if missing:
        warn("missing tools: " + ", ".join(missing))
        info("The GitHub Actions release bundles zsign/ldid in ./bin next to ipatool.exe.")
    else:
        ok("all backends present")


def cmd_inspect(a):
    p = Path(a.file)
    suffix = p.suffix.lower()
    if suffix in (".mobileprovision", ".provisionprofile"):
        prof = prof_mod.load(p)
        info(f"provisioning profile: {p.name}")
        _table(prof_mod.summary(prof))
    elif suffix in (".p12", ".pfx"):
        key, cert, extra = certs_mod.load_p12(p, a.password)
        info(f"certificate: {p.name}")
        _table(certs_mod.cert_summary(cert))
        print(f"    {'Private key':22} {'present' if key else 'MISSING'}")
        if extra:
            print(f"    {'Chain certs':22} {len(extra)}")
    elif suffix in (".cer", ".pem", ".crt", ".der"):
        from cryptography import x509
        raw = p.read_bytes()
        cert = x509.load_pem_x509_certificate(raw) if raw.lstrip().startswith(b"-----") \
            else x509.load_der_x509_certificate(raw)
        _table(certs_mod.cert_summary(cert))
    else:
        raise ToolError(f"don't know how to inspect '{suffix}'. Use a .p12/.mobileprovision/.cer")


def cmd_info(a):
    with tempdir() as tmp:
        ipa = resolve_ipa(a.ipa, tmp)
        with zipfile.ZipFile(ipa) as zf:
            names = zf.namelist()
            info_name = next((n for n in names if n.endswith(".app/Info.plist")), None)
            if not info_name:
                raise ToolError("no Info.plist found; is this a valid IPA?")
            data = plistlib.loads(zf.read(info_name))
            info(f"app: {ipa.name}")
            _table(plist_edit.summary(data))
            mp = next((n for n in names if n.endswith("embedded.mobileprovision")), None)
            if mp:
                prof = prof_mod.loads(zf.read(mp))
                print()
                info("embedded provisioning profile:")
                _table(prof_mod.summary(prof))
            else:
                warn("no embedded.mobileprovision (App Store build)")


def cmd_pull_cert(a):
    extract.pull(a.ipa, a.out, dump_chain=not a.no_chain)


def cmd_sign(a):
    sign_mod.sign_ipa(
        a.ipa, a.output,
        p12=a.p12, password=a.password, key=a.key, cert=a.cert, prov=a.prov,
        bundle_id=a.bundle_id, name=a.name, version=a.version,
        entitlements=a.entitlements, dylibs=a.inject, weak=a.weak,
        zip_level=a.zip, install=a.install, quiet=a.quiet,
    )


def cmd_fakesign(a):
    fakesign_mod.fakesign_ipa(a.ipa, a.output, entitlements=a.entitlements, zip_level=a.zip)


def cmd_convert(a):
    key, cert, extra = certs_mod.load_p12(a.p12, a.password)
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    if a.cert_out:
        Path(a.cert_out).write_bytes(certs_mod.to_pem(cert)); ok(f"cert -> {a.cert_out}")
    if a.key_out:
        if not key:
            raise ToolError("no private key in this .p12")
        Path(a.key_out).write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
        ok(f"key  -> {a.key_out}")
    if not (a.cert_out or a.key_out):
        warn("nothing written; pass --cert-out and/or --key-out")


def cmd_install(a):   device.install(resolve_ipa_local(a.ipa))
def cmd_listapps(a):  device.list_apps()
def cmd_udid(a):      device.device_info()


def resolve_ipa_local(x):
    if not Path(x).is_file():
        raise ToolError(f"file not found: {x}")
    return x


# ---------------- parser ----------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ipatool",
        description="Windows-friendly IPA signing & inspection multitool "
                    "(re-sign, inspect certs/profiles, pull certs, install). "
                    "Does not bypass MDM or forge Apple certificates.",
    )
    p.add_argument("-V", "--version", action="version", version=f"ipatool {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("doctor", help="check which backends (zsign/ldid/libimobiledevice) are available")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("inspect", help="inspect a .p12 / .mobileprovision / .cer")
    sp.add_argument("file")
    sp.add_argument("-p", "--password", help="password for a .p12")
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("info", help="show an IPA's Info.plist + embedded profile (accepts a URL)")
    sp.add_argument("ipa")
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("pull-cert", help="extract the profile + signer cert chain from an IPA or URL")
    sp.add_argument("ipa", help="path to .ipa or an http(s) URL")
    sp.add_argument("-o", "--out", default="pulled", help="output directory (default: ./pulled)")
    sp.add_argument("--no-chain", action="store_true", help="skip Mach-O signer-chain extraction")
    sp.set_defaults(func=cmd_pull_cert)

    sp = sub.add_parser("sign", help="re-sign an IPA with your certificate (via zsign)")
    sp.add_argument("ipa")
    sp.add_argument("-o", "--output", required=True, help="output .ipa path")
    sp.add_argument("--p12", help="signing .p12/.pfx")
    sp.add_argument("-p", "--password", help="password for the .p12")
    sp.add_argument("--key", help="private key .pem (alternative to --p12)")
    sp.add_argument("--cert", help="certificate .pem (with --key)")
    sp.add_argument("-m", "--prov", help="matching .mobileprovision")
    sp.add_argument("-b", "--bundle-id", help="override CFBundleIdentifier")
    sp.add_argument("-n", "--name", help="override display name")
    sp.add_argument("-r", "--version", help="override CFBundleShortVersionString")
    sp.add_argument("-e", "--entitlements", help="entitlements .plist to apply")
    sp.add_argument("-l", "--inject", action="append", metavar="DYLIB", help="inject a dylib (repeatable)")
    sp.add_argument("--weak", action="store_true", help="inject dylibs as weak references")
    sp.add_argument("--zip", type=int, default=9, help="output zip level 0-9 (default 9)")
    sp.add_argument("-i", "--install", action="store_true", help="install to a USB device after signing")
    sp.add_argument("-q", "--quiet", action="store_true")
    sp.set_defaults(func=cmd_sign)

    sp = sub.add_parser("fakesign", help="ad-hoc sign an IPA with ldid (for jailbroken devices)")
    sp.add_argument("ipa")
    sp.add_argument("-o", "--output", required=True)
    sp.add_argument("-e", "--entitlements", help="entitlements .plist")
    sp.add_argument("--zip", type=int, default=9)
    sp.set_defaults(func=cmd_fakesign)

    sp = sub.add_parser("convert", help="export cert/key PEM from a .p12")
    sp.add_argument("p12")
    sp.add_argument("-p", "--password")
    sp.add_argument("--cert-out")
    sp.add_argument("--key-out")
    sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("install", help="install an IPA to a USB device (libimobiledevice)")
    sp.add_argument("ipa"); sp.set_defaults(func=cmd_install)

    sp = sub.add_parser("list-apps", help="list apps installed on a USB device")
    sp.set_defaults(func=cmd_listapps)

    sp = sub.add_parser("device", help="show connected device info / UDID")
    sp.set_defaults(func=cmd_udid)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except ToolError as e:
        err(str(e)); return 1
    except KeyboardInterrupt:
        err("interrupted"); return 130


if __name__ == "__main__":
    sys.exit(main())
