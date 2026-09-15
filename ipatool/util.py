"""Shared helpers: colored logging, subprocess runner, downloads, temp dirs."""
from __future__ import annotations
import subprocess, sys, os, tempfile, shutil, urllib.request, contextlib
from pathlib import Path

def _isatty() -> bool:
    try:
        return sys.stdout is not None and sys.stdout.isatty()
    except Exception:
        return False


_USE_COLOR = _isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s


def info(msg: str) -> None:  print(_c("36", "[*] ") + msg)
def ok(msg: str) -> None:    print(_c("32", "[+] ") + msg)
def warn(msg: str) -> None:  print(_c("33", "[!] ") + msg)
def err(msg: str) -> None:   print(_c("31", "[x] ") + msg, file=sys.stderr)


class ToolError(Exception):
    """User-facing error; CLI prints it without a traceback."""


def run(cmd: list[str], *, check: bool = True, capture: bool = False,
        cwd: str | os.PathLike | None = None) -> subprocess.CompletedProcess:
    """Run a command. Raises ToolError on failure when check=True."""
    proc = subprocess.run(
        cmd, cwd=cwd, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ToolError(f"`{cmd[0]}` failed (exit {proc.returncode})" + (f":\n{detail}" if detail else ""))
    return proc


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def download(url: str, dest: str | os.PathLike) -> Path:
    """Download url to dest with a simple progress line."""
    dest = Path(dest)
    info(f"downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "ipatool"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        got = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total:
                pct = got * 100 // total
                print(f"\r    {pct:3d}%  {got >> 20} / {total >> 20} MiB", end="", flush=True)
        if total:
            print()
    ok(f"saved {dest} ({dest.stat().st_size >> 20} MiB)")
    return dest


def resolve_ipa(path_or_url: str, workdir: Path) -> Path:
    """Return a local IPA path, downloading first if a URL was given."""
    if is_url(path_or_url):
        name = path_or_url.rstrip("/").split("/")[-1] or "download.ipa"
        if not name.lower().endswith(".ipa"):
            name += ".ipa"
        return download(path_or_url, workdir / name)
    p = Path(path_or_url)
    if not p.is_file():
        raise ToolError(f"file not found: {p}")
    return p


@contextlib.contextmanager
def tempdir(prefix: str = "ipatool-"):
    d = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def find_app_dir(payload_or_extract: Path) -> Path:
    """Given an extracted IPA root (containing Payload/) or a Payload dir,
    return the .app directory."""
    root = payload_or_extract
    payload = root / "Payload" if (root / "Payload").is_dir() else root
    apps = sorted(payload.glob("*.app"))
    if not apps:
        raise ToolError(f"no .app bundle found under {payload}")
    return apps[0]
