"""ipatool GUI - a dark, animated desktop front-end (no console).

Wraps the same backend as the CLI: inspect certs/profiles, pull certs from an
IPA/URL (with provisioned-device UDIDs + entitlements), and re-sign with easy
cert/profile swapping. No .p12 password cracking -- that's credential theft.
"""
from __future__ import annotations
import sys, os, io, queue, threading, colorsys, zipfile, plistlib
import tkinter as tk
from tkinter import ttk, filedialog, font as tkfont

from . import __version__, certs as certs_mod, profile as prof_mod, sign as sign_mod, extract, bins

# ---- palette ----
BG      = "#0b0d17"
PANEL   = "#121629"
PANEL2  = "#0e1120"
INK     = "#e7ecff"
MUTE    = "#8a93b8"
ACCENT  = "#38f2c8"
ACCENT2 = "#8a5cff"
DANGER  = "#ff5d73"
MONO    = "Consolas"


def hsv_hex(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


# ============================ animated title ============================
class Banner(tk.Canvas):
    TEXT = "J3NSONTOP"

    def __init__(self, master, height=118):
        super().__init__(master, height=height, bg=BG, highlightthickness=0)
        self.h = height
        self.phase = 0.0
        self.font = tkfont.Font(family="Impact", size=52, weight="bold")
        if "impact" not in self.font.actual("family").lower():
            self.font = tkfont.Font(family="Arial Black", size=48, weight="bold")
        self.sub = tkfont.Font(family=MONO, size=11)
        self.stars = []
        self.bind("<Configure>", lambda e: self._seed_stars())
        self._seed_stars()
        self._tick()

    def _seed_stars(self):
        import random
        w = max(self.winfo_width(), 700)
        self.stars = [(random.random() * w, random.random() * self.h,
                       random.random()) for _ in range(60)]

    def _tick(self):
        self.delete("all")
        w = max(self.winfo_width(), 700)
        # drifting starfield
        for i, (x, y, sp) in enumerate(self.stars):
            x = (x + 0.3 + sp) % w
            self.stars[i] = (x, y, sp)
            b = 0.25 + 0.4 * sp
            self.create_oval(x, y, x + 1.6, y + 1.6, outline="",
                             fill=hsv_hex(0.55, 0.2, b))
        # per-letter neon hue wave
        widths = [self.font.measure(c) for c in self.TEXT]
        total = sum(widths) + (len(self.TEXT) - 1) * 6
        x = (w - total) / 2
        cy = self.h / 2 - 6
        for i, c in enumerate(self.TEXT):
            hue = (self.phase + i * 0.075) % 1.0
            glow = hsv_hex(hue, 0.9, 0.45)
            bright = hsv_hex(hue, 0.65, 1.0)
            cx = x + widths[i] / 2
            for dx, dy in ((0, 3), (2, 0), (-2, 0), (0, -2)):        # cheap glow
                self.create_text(cx + dx, cy + dy, text=c, font=self.font, fill=glow)
            self.create_text(cx, cy, text=c, font=self.font, fill=bright)
            x += widths[i] + 6
        # tagline + underline sweep
        self.create_text(w / 2, self.h - 20, text="I P A   M U L T I T O O L",
                         font=self.sub, fill=MUTE)
        sweep = (self.phase * 2) % 1.0
        lx = w * 0.5 + (sweep - 0.5) * total
        self.create_line(lx - 40, self.h - 8, lx + 40, self.h - 8,
                         fill=hsv_hex(self.phase, 0.7, 1.0), width=2)
        self.phase = (self.phase + 0.012) % 1.0
        self.after(33, self._tick)


# ============================ output plumbing ============================
class _QueueWriter(io.TextIOBase):
    def __init__(self, q): self.q = q
    def write(self, s):
        if s:
            self.q.put(s)
        return len(s)
    def flush(self): pass


# ============================ main app ============================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"ipatool {__version__}  -  J3NSONTOP")
        self.configure(bg=BG)
        self.geometry("880x680")
        self.minsize(760, 560)
        self._busy = False
        self.q: queue.Queue = queue.Queue()

        Banner(self).pack(fill="x")

        nav = tk.Frame(self, bg=PANEL2)
        nav.pack(fill="x")
        self.pages: dict[str, tk.Frame] = {}
        self.navbtns: dict[str, tk.Label] = {}
        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        self.content = content

        for name, builder in (("Inspect", self._build_inspect),
                              ("Pull Certs", self._build_pull),
                              ("Sign", self._build_sign),
                              ("About", self._build_about)):
            page = tk.Frame(content, bg=BG)
            builder(page)
            self.pages[name] = page
            lbl = tk.Label(nav, text=name, font=(MONO, 11, "bold"), fg=MUTE, bg=PANEL2,
                           padx=18, pady=10, cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, n=name: self.show(n))
            self.navbtns[name] = lbl

        # log console
        logwrap = tk.Frame(self, bg=PANEL)
        logwrap.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        tk.Label(logwrap, text="OUTPUT", font=(MONO, 9, "bold"), fg=ACCENT, bg=PANEL,
                 anchor="w").pack(fill="x", padx=8, pady=(6, 0))
        self.log = tk.Text(logwrap, bg=PANEL2, fg=INK, insertbackground=INK,
                           font=(MONO, 10), relief="flat", height=12, wrap="word",
                           padx=10, pady=8)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
        self.log.tag_config("ok", foreground=ACCENT)
        self.log.tag_config("err", foreground=DANGER)
        self.log.tag_config("hi", foreground=ACCENT2)

        self.show("Inspect")
        self._log(f"ipatool {__version__} ready. Backends: "
                  + ", ".join(f"{k}={'ok' if v else 'missing'}" for k, v in bins.status().items()) + "\n")

    # ---------- helpers ----------
    def show(self, name):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        for n, lbl in self.navbtns.items():
            lbl.config(fg=ACCENT if n == name else MUTE,
                       bg=PANEL if n == name else PANEL2)

    def _log(self, text, tag=None):
        self.log.insert("end", text, tag or ())
        self.log.see("end")

    def _pick(self, var, patterns, save=False):
        kw = dict(filetypes=patterns)
        path = filedialog.asksaveasfilename(**kw) if save else filedialog.askopenfilename(**kw)
        if path:
            var.set(path)

    def _pickdir(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def run_task(self, fn, *, clear=True):
        """Run a backend fn in a thread, streaming its stdout into the log."""
        if self._busy:
            self._log("\n[busy] wait for the current task to finish\n", "err")
            return
        self._busy = True
        if clear:
            self.log.delete("1.0", "end")

        old_out, old_err = sys.stdout, sys.stderr
        w = _QueueWriter(self.q)
        sys.stdout = sys.stderr = w

        def worker():
            try:
                fn()
            except Exception as e:
                self.q.put(f"\n[x] {e}\n")
            finally:
                self.q.put(None)  # sentinel

        threading.Thread(target=worker, daemon=True).start()

        def pump():
            drained = False
            try:
                while True:
                    item = self.q.get_nowait()
                    if item is None:
                        sys.stdout, sys.stderr = old_out, old_err
                        self._busy = False
                        drained = True
                        break
                    tag = "err" if item.lstrip().startswith("[x]") else \
                          ("ok" if item.lstrip().startswith("[+]") else None)
                    self._log(item, tag)
            except queue.Empty:
                pass
            if not drained:
                self.after(40, pump)
        self.after(40, pump)

    # ---------- pages ----------
    def _row(self, parent, label):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", pady=4)
        tk.Label(f, text=label, width=12, anchor="w", font=(MONO, 10),
                 fg=MUTE, bg=BG).pack(side="left")
        return f

    def _entry(self, frame, var, width=48):
        e = tk.Entry(frame, textvariable=var, font=(MONO, 10), bg=PANEL2, fg=INK,
                     insertbackground=INK, relief="flat", width=width)
        e.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=4)
        return e

    def _btn(self, parent, text, cmd, kind="ghost"):
        colors = {"go": (ACCENT, "#04121a"), "alt": (ACCENT2, "#0a0620"),
                  "ghost": (PANEL, INK)}
        bgc, fgc = colors[kind]
        b = tk.Label(parent, text=text, font=(MONO, 10, "bold"), bg=bgc, fg=fgc,
                     padx=14, pady=7, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _build_inspect(self, page):
        tk.Label(page, text="Inspect a .p12 / .mobileprovision / .cer / .ipa",
                 font=(MONO, 12, "bold"), fg=INK, bg=BG, anchor="w").pack(fill="x", pady=(2, 8))
        self.i_file = tk.StringVar()
        self.i_pw = tk.StringVar()
        r = self._row(page, "File")
        self._entry(r, self.i_file)
        self._btn(r, "Browse", lambda: self._pick(self.i_file, [
            ("iOS files", "*.ipa *.p12 *.pfx *.mobileprovision *.cer *.pem *.der"),
            ("All", "*.*")])).pack(side="left")
        r = self._row(page, ".p12 pass")
        self._entry(r, self.i_pw, width=24)
        self._btn(r, "Inspect", self._do_inspect, "go").pack(side="left")

    def _build_pull(self, page):
        tk.Label(page, text="Pull the profile + signing cert chain from an IPA or URL",
                 font=(MONO, 12, "bold"), fg=INK, bg=BG, anchor="w").pack(fill="x", pady=(2, 8))
        self.p_src = tk.StringVar()
        self.p_out = tk.StringVar(value=os.path.join(os.getcwd(), "pulled"))
        r = self._row(page, "IPA / URL")
        self._entry(r, self.p_src)
        self._btn(r, "Browse", lambda: self._pick(self.p_src, [("IPA", "*.ipa"), ("All", "*.*")])).pack(side="left")
        r = self._row(page, "Output dir")
        self._entry(r, self.p_out)
        self._btn(r, "...", lambda: self._pickdir(self.p_out)).pack(side="left")
        r = tk.Frame(page, bg=BG); r.pack(fill="x", pady=10)
        self._btn(r, "Pull certs", self._do_pull, "go").pack(side="left", padx=(0, 8))
        self._btn(r, "Open folder", lambda: self._open(self.p_out.get()), "alt").pack(side="left")

    def _build_sign(self, page):
        tk.Label(page, text="Re-sign an IPA  (swap cert / profile / entitlements freely)",
                 font=(MONO, 12, "bold"), fg=INK, bg=BG, anchor="w").pack(fill="x", pady=(2, 6))
        self.s = {k: tk.StringVar() for k in
                  ("ipa", "p12", "pw", "prov", "ent", "bid", "name", "ver", "out")}
        def filerow(label, key, pats):
            r = self._row(page, label)
            self._entry(r, self.s[key])
            self._btn(r, "Browse", lambda: self._pick(self.s[key], pats)).pack(side="left")
        filerow("IPA", "ipa", [("IPA", "*.ipa")])
        filerow("Cert .p12", "p12", [("PKCS12", "*.p12 *.pfx")])
        r = self._row(page, "Password"); self._entry(r, self.s["pw"], width=24)
        filerow("Profile", "prov", [("Provisioning", "*.mobileprovision")])
        filerow("Entitle", "ent", [("plist", "*.plist *.entitlements"), ("All", "*.*")])
        r = self._row(page, "Bundle ID"); self._entry(r, self.s["bid"])
        r = self._row(page, "Name / Ver")
        self._entry(r, self.s["name"], width=22)
        self._entry(r, self.s["ver"], width=12)
        filerow("Output IPA", "out", [("IPA", "*.ipa")])
        r = tk.Frame(page, bg=BG); r.pack(fill="x", pady=10)
        self._btn(r, "SIGN", self._do_sign, "go").pack(side="left")
        tk.Label(page, text="Needs zsign in ./bin or PATH. Uses YOUR cert+key; the private key is never pulled from an IPA.",
                 font=(MONO, 8), fg=MUTE, bg=BG, anchor="w").pack(fill="x", pady=(2, 0))

    def _build_about(self, page):
        for text, col, sz in (
            (f"ipatool {__version__}", ACCENT, 14),
            ("github.com/jenslazar1-sketch/ipa-multitool", ACCENT2, 10),
            ("", INK, 6),
            ("Signs and inspects IPAs. Pull-cert recovers PUBLIC certs +", INK, 10),
            ("the provisioning profile only -- an IPA never contains the", INK, 10),
            ("private signing key, so it cannot be extracted here.", INK, 10),
            ("", INK, 6),
            ("No MDM bypass. No .p12 password cracking (that is credential", MUTE, 9),
            ("theft). Use your own certificate to sign your own apps.", MUTE, 9),
        ):
            tk.Label(page, text=text, font=(MONO, sz, "bold" if col == ACCENT else "normal"),
                     fg=col, bg=BG, anchor="w").pack(fill="x")

    # ---------- actions ----------
    def _open(self, path):
        try:
            os.startfile(path)  # noqa
        except Exception as e:
            self._log(f"[x] {e}\n", "err")

    def _do_inspect(self):
        path, pw = self.i_file.get().strip(), self.i_pw.get()
        if not path:
            self._log("[x] pick a file first\n", "err"); return
        self.run_task(lambda: _inspect_any(path, pw))

    def _do_pull(self):
        src, out = self.p_src.get().strip(), self.p_out.get().strip()
        if not src:
            self._log("[x] give an IPA path or URL\n", "err"); return
        self.run_task(lambda: extract.pull(src, out))

    def _do_sign(self):
        s = {k: v.get().strip() for k, v in self.s.items()}
        if not (s["ipa"] and s["out"]):
            self._log("[x] need at least an IPA and an output path\n", "err"); return
        self.run_task(lambda: sign_mod.sign_ipa(
            s["ipa"], s["out"], p12=s["p12"] or None, password=s["pw"] or None,
            prov=s["prov"] or None, entitlements=s["ent"] or None,
            bundle_id=s["bid"] or None, name=s["name"] or None, version=s["ver"] or None))


# ---- inspect dispatch shared by GUI ----
def _inspect_any(path, pw):
    from .util import info, ok, warn
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ipa":
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            ip = next((n for n in names if n.endswith(".app/Info.plist")), None)
            if ip:
                d = plistlib.loads(zf.read(ip))
                info(f"app: {os.path.basename(path)}")
                for k in ("CFBundleIdentifier", "CFBundleDisplayName", "CFBundleShortVersionString"):
                    if k in d:
                        print(f"    {k:26} {d[k]}")
            mp = next((n for n in names if n.endswith("embedded.mobileprovision")), None)
            if mp:
                _dump_profile(prof_mod.loads(zf.read(mp)))
            else:
                warn("no embedded profile (App Store build)")
    elif ext in (".mobileprovision", ".provisionprofile"):
        _dump_profile(prof_mod.load(path))
    elif ext in (".p12", ".pfx"):
        key, cert, extra = certs_mod.load_p12(path, pw or None)
        info(f"certificate: {os.path.basename(path)}")
        for k, v in certs_mod.cert_summary(cert):
            print(f"    {k:22} {v}")
        print(f"    {'Private key':22} {'present' if key else 'MISSING'}")
    else:
        from cryptography import x509
        raw = open(path, "rb").read()
        cert = x509.load_pem_x509_certificate(raw) if raw.lstrip().startswith(b"-----") \
            else x509.load_der_x509_certificate(raw)
        for k, v in certs_mod.cert_summary(cert):
            print(f"    {k:22} {v}")


def _dump_profile(prof):
    from .util import info
    info("provisioning profile:")
    for k, v in prof_mod.summary(prof):
        print(f"    {k:22} {v}")
    udids = prof_mod.provisioned_udids(prof)
    if udids:
        print(f"\n    provisioned device UDIDs ({len(udids)}):")
        for u in udids:
            print(f"      - {u}")
    ent = prof_mod.entitlements(prof)
    if ent:
        print("\n    entitlements:")
        for k in sorted(ent):
            print(f"      {k} = {ent[k]}")


def main():
    App().mainloop()
    return 0


if __name__ == "__main__":
    main()
