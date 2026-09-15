"""Certificate handling: inspect .p12, and extract the signing certificate
chain embedded in a signed Mach-O binary.

NOTE: a signed IPA contains only PUBLIC certificates. The private key used to
sign never ships inside an app, so it cannot be recovered here. This module is
for inspection, conversion, and profile/cert extraction -- not key theft.
"""
from __future__ import annotations
import struct, datetime
from pathlib import Path
from .util import ToolError

try:
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, pkcs7
    from cryptography import x509
    _HAVE_CRYPTO = True
except Exception:                                            # pragma: no cover
    _HAVE_CRYPTO = False


def _need_crypto():
    if not _HAVE_CRYPTO:
        raise ToolError("the 'cryptography' package is required (pip install cryptography)")


# ---------- X.509 summaries ----------

def _name_attr(name, oid):
    try:
        return name.get_attributes_for_oid(oid)[0].value
    except Exception:
        return ""


def cert_summary(cert) -> list[tuple[str, str]]:
    from cryptography.x509.oid import NameOID
    subj, iss = cert.subject, cert.issuer
    try:
        not_after = cert.not_valid_after_utc
        now = datetime.datetime.now(datetime.timezone.utc)
    except AttributeError:                                   # older cryptography
        not_after = cert.not_valid_after
        now = datetime.datetime.utcnow()
    expired = not_after < now
    return [
        ("Common name", _name_attr(subj, NameOID.COMMON_NAME)),
        ("Team (OU)", _name_attr(subj, NameOID.ORGANIZATIONAL_UNIT_NAME)),
        ("Org", _name_attr(subj, NameOID.ORGANIZATION_NAME)),
        ("Issuer", _name_attr(iss, NameOID.COMMON_NAME)),
        ("Serial", format(cert.serial_number, "x")),
        ("Valid until", not_after.strftime("%Y-%m-%d %H:%M UTC") + ("  (EXPIRED)" if expired else "")),
    ]


def load_p12(path: str | Path, password: str | None):
    """Return (private_key, cert, extra_certs) from a .p12/.pfx."""
    _need_crypto()
    data = Path(path).read_bytes()
    pw = password.encode() if password else None
    try:
        key, cert, extra = pkcs12.load_key_and_certificates(data, pw)
    except Exception as e:
        raise ToolError(f"could not open .p12 (wrong password?): {e}")
    return key, cert, extra or []


def cert_from_der(der: bytes):
    _need_crypto()
    return x509.load_der_x509_certificate(der)


def to_pem(cert) -> bytes:
    return cert.public_bytes(Encoding.PEM)


# ---------- Mach-O code-signature certificate extraction ----------
# Layout refs: <mach-o/loader.h>, cs_blobs.h
_MH_MAGIC_64, _MH_CIGAM_64 = 0xFEEDFACF, 0xCFFAEDFE
_MH_MAGIC, _MH_CIGAM = 0xFEEDFACE, 0xCEFAEDFE
_FAT_MAGIC, _FAT_CIGAM = 0xCAFEBABE, 0xBEBAFECE
_LC_CODE_SIGNATURE = 0x1D
_CSMAGIC_EMBEDDED_SIGNATURE = 0xFADE0CC0
_CSMAGIC_BLOBWRAPPER = 0xFADE0B01                            # wraps the CMS/PKCS7


def _macho_slices(data: bytes):
    """Yield (offset, is_le) for each Mach-O slice (handles fat binaries)."""
    magic = struct.unpack_from(">I", data, 0)[0]
    if magic in (_FAT_MAGIC, _FAT_CIGAM):
        nfat = struct.unpack_from(">I", data, 4)[0]
        for i in range(nfat):
            off = struct.unpack_from(">I", data, 8 + i * 20 + 8)[0]
            sub = struct.unpack_from(">I", data, off)[0]
            yield off, sub in (_MH_CIGAM_64, _MH_CIGAM)
    else:
        yield 0, magic in (_MH_CIGAM_64, _MH_CIGAM)


def _find_code_signature(data: bytes, off: int, le: bool) -> tuple[int, int] | None:
    end = "<" if le else ">"
    magic = struct.unpack_from(end + "I", data, off)[0]
    is64 = magic in (_MH_MAGIC_64, _MH_CIGAM_64)
    ncmds = struct.unpack_from(end + "I", data, off + 16)[0]
    p = off + (32 if is64 else 28)
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from(end + "II", data, p)
        if cmd == _LC_CODE_SIGNATURE:
            dataoff, datasize = struct.unpack_from(end + "II", data, p + 8)
            return off + dataoff, datasize
        p += cmdsize
    return None


def _pkcs7_from_superblob(blob: bytes) -> bytes | None:
    # SuperBlob is big-endian regardless of the Mach-O byte order.
    if struct.unpack_from(">I", blob, 0)[0] != _CSMAGIC_EMBEDDED_SIGNATURE:
        return None
    count = struct.unpack_from(">I", blob, 8)[0]
    for i in range(count):
        blob_off = struct.unpack_from(">I", blob, 12 + i * 8 + 4)[0]
        bmagic, blen = struct.unpack_from(">II", blob, blob_off)
        if bmagic == _CSMAGIC_BLOBWRAPPER:
            return blob[blob_off + 8: blob_off + blen]
    return None


def certs_from_macho(path: str | Path) -> list:
    """Return the X.509 certs embedded in a Mach-O's code signature."""
    _need_crypto()
    data = Path(path).read_bytes()
    for off, le in _macho_slices(data):
        cs = _find_code_signature(data, off, le)
        if not cs:
            continue
        sig_off, sig_len = cs
        der = _pkcs7_from_superblob(data[sig_off: sig_off + sig_len])
        if not der:
            continue
        try:
            certs = pkcs7.load_der_pkcs7_certificates(der)
            if certs:
                return certs
        except Exception:
            continue
    return []
