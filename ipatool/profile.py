"""Parse .mobileprovision provisioning profiles.

A .mobileprovision is a CMS (PKCS#7) signed message wrapping an XML plist.
We recover the plist and surface the useful fields.
"""
from __future__ import annotations
import plistlib, datetime
from pathlib import Path
from .util import ToolError


def _extract_plist_bytes(raw: bytes) -> bytes:
    start = raw.find(b"<?xml")
    end = raw.rfind(b"</plist>")
    if start == -1 or end == -1:
        raise ToolError("could not locate the plist inside the provisioning profile")
    return raw[start:end + len(b"</plist>")]


def loads(raw: bytes) -> dict:
    return plistlib.loads(_extract_plist_bytes(raw))


def load(path: str | Path) -> dict:
    return loads(Path(path).read_bytes())


def developer_cert_ders(prof: dict) -> list[bytes]:
    """DER bytes of every certificate the profile authorizes for signing."""
    return [bytes(c) for c in prof.get("DeveloperCertificates", [])]


def _fmt_date(d) -> str:
    if isinstance(d, datetime.datetime):
        return d.strftime("%Y-%m-%d %H:%M UTC")
    return str(d)


def is_expired(prof: dict) -> bool:
    exp = prof.get("ExpirationDate")
    if isinstance(exp, datetime.datetime):
        now = datetime.datetime.now(exp.tzinfo) if exp.tzinfo else datetime.datetime.utcnow()
        return exp < now
    return False


def summary(prof: dict) -> list[tuple[str, str]]:
    ent = prof.get("Entitlements", {}) or {}
    devices = prof.get("ProvisionedDevices")
    rows = [
        ("Name", str(prof.get("Name", ""))),
        ("App ID name", str(prof.get("AppIDName", ""))),
        ("Team", f"{prof.get('TeamName','')} ({', '.join(prof.get('TeamIdentifier', []))})"),
        ("App ID", str(ent.get("application-identifier", ""))),
        ("Created", _fmt_date(prof.get("CreationDate"))),
        ("Expires", _fmt_date(prof.get("ExpirationDate")) + ("  (EXPIRED)" if is_expired(prof) else "")),
        ("Xcode managed", str(prof.get("IsXcodeManaged", False))),
        ("get-task-allow", str(ent.get("get-task-allow", False))),
        ("aps-environment", str(ent.get("aps-environment", "-"))),
        ("Type", "Development" if devices else "Distribution (App Store / Enterprise)"),
        ("Provisioned devices", str(len(devices)) if devices else "0 (not device-limited)"),
        ("Signing certs", str(len(developer_cert_ders(prof)))),
    ]
    return rows
