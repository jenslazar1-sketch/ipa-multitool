# ipatool — IPA signing & inspection multitool (Windows)

A single-command toolkit for working with iOS `.ipa` files on Windows:
re-sign apps for sideloading with your own certificate, inspect and pull
certificates / provisioning profiles, edit bundle metadata, inject your own
dylibs, and install to a USB-connected device.

> **Scope / ethics.** This tool signs and inspects apps. It **does not** bypass
> Mobile Device Management (MDM), defeat VPN/DNS restrictions set by a device's
> administrator, or forge/crack Apple certificates. Certificate "pulling" only
> recovers the **public** certificate + provisioning profile that already ship
> inside an IPA — the private signing key is never inside an app and cannot be
> extracted. Use it on apps and devices you're allowed to.

## Install

**Easiest:** grab `ipatool-windows-x64.zip` from the [Releases](../../releases)
page (built by GitHub Actions — bundles `zsign.exe`, `ldid.exe` and the needed
DLLs in `bin/`). Unzip and run `ipatool.exe` from a terminal.

**From source:**
```
pip install -r requirements.txt
python run.py --help
```
The native backends (`zsign`, `ldid`, `libimobiledevice`) go in a `bin/` folder
next to the tool, or anywhere on your `PATH`. Run `ipatool doctor` to see what's
detected.

## Commands

```
ipatool doctor                 # what backends are available
ipatool inspect FILE           # inspect a .p12 / .mobileprovision / .cer
ipatool info IPA|URL           # show Info.plist + embedded profile
ipatool pull-cert IPA|URL -o DIR   # extract profile + signer cert chain
ipatool sign IPA -o OUT ...    # re-sign with your certificate (zsign)
ipatool fakesign IPA -o OUT    # ad-hoc sign for jailbroken devices (ldid)
ipatool convert P12 --cert-out c.pem --key-out k.pem
ipatool install IPA            # install to USB device (libimobiledevice)
ipatool device                 # show connected device / UDID
ipatool list-apps              # list installed apps
```

### Re-sign an IPA
```
ipatool sign MyApp.ipa -o MyApp-signed.ipa ^
  --p12 dev.p12 -p mypassword ^
  --prov dev.mobileprovision ^
  --bundle-id com.me.myapp --name "My App"
```
Inject your own tweak dylibs while signing:
```
ipatool sign MyApp.ipa -o MyApp-tweaked.ipa --p12 dev.p12 -p pw --prov dev.mobileprovision ^
  --inject MyTweak.dylib --inject libsub.dylib
```

### Pull the certificate & profile out of an IPA (or a download)
```
ipatool pull-cert https://example.com/some.ipa -o pulled
```
Writes `*.mobileprovision`, `*.profile-cert*.pem` (certs the profile authorizes)
and `*.signer*.pem` (the actual code-signing chain from the Mach-O), and prints
a summary of each. Remember: **public certs only**, never the private key.

### Inspect a certificate or profile
```
ipatool inspect dev.p12 -p mypassword
ipatool inspect dev.mobileprovision
```
Shows team ID, expiry, entitlements, provisioned device count, Xcode-managed
flag, etc.

## Backends

| Backend | Used for | Source |
|---|---|---|
| [zsign](https://github.com/zhlynn/zsign) | signing / dylib injection | built by CI |
| [ldid](https://github.com/ProcursusTeam/ldid) | fakesign (jailbroken) | built by CI |
| [libimobiledevice](https://libimobiledevice.org) | device install / info | install separately |

## Building it yourself (GitHub Actions)

Push to GitHub — the `build` workflow compiles `zsign` (and `ldid`) for Windows
via MSYS2, packages `ipatool.exe` with PyInstaller, and uploads
`ipatool-windows-x64.zip` as a build artifact. Push a `v*` tag to also publish a
GitHub Release.

## License

MIT.
