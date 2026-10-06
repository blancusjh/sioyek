# Matching releases on macOS and PHANEX

On the Mac, run:

```sh
~/.local/bin/sioyek-sync
```

This selects the latest published release from `blancusjh/sioyek`, installs its
Apple Silicon Mac build, and sends the **same release tag** to PHANEX over SSH.
It verifies archive and executable SHA-256 hashes before replacing either app.
PHANEX uses the Arch Linux x86_64 build and its system Qt libraries.

Check both machines without installing, or select an older release:

```sh
~/.local/bin/sioyek-sync --check
~/.local/bin/sioyek-sync --tag personal-build-fc7c4a93
```

Reopen Sioyek after an update. Preferences, reading databases, and annotations
stay in their existing locations. Previous app directories are retained for
rollback. macOS installs to `/Applications/sioyek.app`; Linux installs under
`~/.local/opt/sioyek/` with a launcher in `~/.local/bin/` and an application menu
entry. Running `sioyek-sync` on PHANEX updates PHANEX only.

The updater requires Python 3.12 or newer. Its installed copy is
`~/.local/share/sioyek-release/sioyek_release.py`, and version records are in
`~/.local/state/sioyek-release/installed.json`. The Mac's SSH targets are in
`~/.config/sioyek-release/targets.json`; SSH credentials stay outside the
repository. SSH uses existing keys and strict host verification.

## Publish the next matching release

Both builds must use the same committed source. The build scripts write a
`BUILD-COMMIT` stamp after compilation. Commit changes before building. Use the
Mac instructions in [BUILDING-MAC.md](BUILDING-MAC.md) and the Linux instructions
in [BUILDING-LINUX.md](BUILDING-LINUX.md).

On the Mac, package the compiled app:

```sh
python3 scripts/sioyek_release.py pack --bundle build/sioyek.app --output release-artifacts
```

On PHANEX, after compiling the same commit:

```sh
MAKE_PARALLEL=4 QMAKE=/usr/bin/qmake6 ./build_linux.sh
python3 scripts/sioyek_release.py pack --bundle build --output release-artifacts
```

Copy PHANEX's `.tar.gz` and `linux-x86_64-arch.json` into the Mac's
`release-artifacts` directory, alongside its Mac ZIP and `macos-arm64.json`.
Then publish from the Mac using authenticated GitHub CLI:

```sh
python3 scripts/sioyek_release.py publish --artifacts release-artifacts --tag personal-build-YYYYMMDD-N
~/.local/bin/sioyek-sync
```

Publishing checks that both builds have the same source commit. It uploads both
packages and `sioyek-release.json` to a draft before publishing the release.
Existing release assets cannot be replaced with different contents. A release
without matching builds and a manifest is rejected by the updater.

The Linux package is built for PHANEX's Arch Linux runtime; it is not a bundled
AppImage for other distributions. The Mac app is ad hoc signed, not notarized.

Updater validation:

```sh
python3 -m unittest discover -s tests -p 'test_sioyek_release.py'
```
